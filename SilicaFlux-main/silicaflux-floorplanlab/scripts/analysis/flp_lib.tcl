# =============================================================================
# SilicaFlux FloorplanLab -- shared Tcl helpers for OpenROAD analysis scripts.
# All data comes from the loaded OpenDB / OpenSTA state; nothing is estimated
# here that the tools did not compute.
# =============================================================================
namespace eval flp {}

proc flp::env {name {default ""}} {
  if {[info exists ::env($name)] && $::env($name) != ""} { return $::env($name) }
  return $default
}

proc flp::jstr {s} {
  set s [string map [list "\\" "\\\\" "\"" "\\\"" "\n" "\\n" "\r" "" "\t" " "] $s]
  return "\"$s\""
}
proc flp::jnum {v} {
  if {$v == "" || [string is double -strict $v] == 0} { return "null" }
  if {$v == "inf" || $v == "-inf" || $v == "nan"} { return "null" }
  return $v
}
proc flp::jlist {items} { return "\[[join $items ,]\]" }
proc flp::jobj {pairs} {
  set out {}
  foreach {k v} $pairs { lappend out "[flp::jstr $k]:$v" }
  return "\{[join $out ,]\}"
}

proc flp::um {dbu} { return [expr {double($dbu) / [[ord::get_db_block] getDefUnits]}] }
proc flp::box_um {b} {
  return [flp::jlist [list [format %.4f [flp::um [$b xMin]]] [format %.4f [flp::um [$b yMin]]] \
                           [format %.4f [flp::um [$b xMax]]] [format %.4f [flp::um [$b yMax]]]]]
}
proc flp::rect_um {r} {
  return [flp::jlist [list [format %.4f [flp::um [$r xMin]]] [format %.4f [flp::um [$r yMin]]] \
                           [format %.4f [flp::um [$r xMax]]] [format %.4f [flp::um [$r yMax]]]]]
}

# Logical groups: FLP_GROUPS = "name1 {pat1 pat2} name2 {pat3} ..." (prefix match,
# first match wins, OpenROAD hierarchy separator '/').
proc flp::group_of {name} {
  foreach {g pats} [flp::env FLP_GROUPS ""] {
    foreach p $pats {
      if {[string first $p $name] == 0} { return $g }
    }
  }
  return "top"
}

proc flp::write_file {path text} {
  file mkdir [file dirname $path]
  set fh [open $path w]
  puts $fh $text
  close $fh
}

proc flp::master_kind {m} {
  set t [$m getType]
  set n [$m getName]
  if {$t == "BLOCK"} { return macro }
  if {[string match -nocase *tap* $n]} { return tapcell }
  if {[string match -nocase *endcap* $n] || $t == "ENDCAP" || [string match ENDCAP* $t]} { return endcap }
  if {[string match -nocase *fill* $n] || $t == "CORE_SPACER"} { return filler }
  if {[string match -nocase *decap* $n]} { return decap }
  if {[string match -nocase *tie* $n] || [string match *conb* $n] || $t == "CORE_TIEHIGH" || $t == "CORE_TIELOW"} { return tie }
  return std
}

proc flp::edge_of {b} {
  set die [[ord::get_db_block] getDieArea]
  set cx [expr {([$b xMin] + [$b xMax]) / 2.0}]
  set cy [expr {([$b yMin] + [$b yMax]) / 2.0}]
  set d [list [expr {$cx - [$die xMin]}] left [expr {[$die xMax] - $cx}] right \
              [expr {$cy - [$die yMin]}] bottom [expr {[$die yMax] - $cy}] top]
  set best ""; set bd 1e30
  foreach {v e} $d { if {$v < $bd} { set bd $v; set best $e } }
  return $best
}
