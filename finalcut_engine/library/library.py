"""Top-level Library: a collection of Events plus library-wide indexes.

Media is indexed once at import time (ratings, keywords, searchable text) so
browsing, filtering, and smart collections never re-scan files (spec section 5).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from finalcut_engine.library.collection import Collection, SmartCollection
from finalcut_engine.library.event import Event
from finalcut_engine.library.keyword import KeywordIndex, KeywordRange
from finalcut_engine.library.ratings import RatingStore
from finalcut_engine.media.asset import MediaAsset
from finalcut_engine.media.importer import MediaImporter


@dataclass
class Library:
    name: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    events: Dict[str, Event] = field(default_factory=dict)
    collections: Dict[str, Collection] = field(default_factory=dict)
    smart_collections: Dict[str, SmartCollection] = field(default_factory=dict)
    ratings: RatingStore = field(default_factory=RatingStore)
    keywords: KeywordIndex = field(default_factory=KeywordIndex)

    # -- organisation ------------------------------------------------------
    def create_event(self, name: str) -> Event:
        event = Event(name=name)
        self.events[event.id] = event
        return event

    def add_collection(self, collection: Collection) -> Collection:
        self.collections[collection.name] = collection
        return collection

    def add_smart_collection(self, smart: SmartCollection) -> SmartCollection:
        self.smart_collections[smart.name] = smart
        return smart

    # -- import --------------------------------------------------------------
    def import_media(self, event: Event, paths: List[Path], importer: MediaImporter) -> List[MediaAsset]:
        assets = importer.import_batch(paths)
        for asset in assets:
            event.add_asset(asset)
        return assets

    # -- indexing / search ---------------------------------------------------
    def all_assets(self) -> List[MediaAsset]:
        result: List[MediaAsset] = []
        for event in self.events.values():
            result.extend(event.asset_list())
        return result

    def find_asset(self, asset_id: str) -> MediaAsset | None:
        for event in self.events.values():
            if asset_id in event.assets:
                return event.assets[asset_id]
        return None

    def tag(self, asset: MediaAsset, keyword: str, range=None) -> None:
        self.keywords.add(KeywordRange(asset_id=asset.id, keyword=keyword, range=range))

    def search(self, query: str) -> List[MediaAsset]:
        q = query.lower().strip()
        if not q:
            return self.all_assets()
        matches = []
        for asset in self.all_assets():
            if q in asset.searchable_text():
                matches.append(asset)
                continue
            if q in {k.lower() for k in self.keywords.keywords_for(asset.id)}:
                matches.append(asset)
        return matches

    def smart_collection_results(self, name: str) -> List[MediaAsset]:
        return self.smart_collections[name].evaluate(self)
