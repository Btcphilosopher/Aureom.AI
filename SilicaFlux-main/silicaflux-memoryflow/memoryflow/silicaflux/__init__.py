"""Repository-evidence layer: the *existing* SilicaFlux RTL, documents and targets.

MemoryFlow v1 was built without access to the SilicaFlux sources.  This
package locates them in the surrounding ``SilicaFlux-main`` tree (inside ZIP
/ tar archives and as loose ``.sf`` files), and

* :mod:`.sources`      extracts every HDL file with sha256 provenance
* :mod:`.hdl`          parses modules, ports, parameters, instances and types
* :mod:`.inventory`    classifies each memory-subsystem block as implemented,
                       behavioural, referenced-only, interface-drifted or
                       documented-only, with file:line evidence
* :mod:`.doc_targets`  the SilicaFlux-V / full-SilicaFlux targets stated in
                       the repository's design documents (with page cites)
* :mod:`.characterise` self-checking testbenches that run the *real*
                       SilicaFlux RTL and measure latency / bandwidth
* :mod:`.baselines`    MemoryFlow system configurations derived from all of
                       the above
"""
