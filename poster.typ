#import "template.typ": *

#import "@preview/cetz:0.4.0": canvas, draw
#import "@preview/cetz-plot:0.1.2": plot
#import "@preview/gentle-clues:1.2.0": *
#import "@preview/codly:1.3.0": *
#import "@preview/codly-languages:0.1.1": *
#show: codly-init.with()


// poster configuration
#set page(
  paper: "a0", 
  margin: 1in, 
  columns: 1  
)

// global styling & colors
#set text(size: 28pt)
#show link: set text(fill: blue)
#show link: underline

#let princeton-zebra-fill = rgb("#a0a0a01a")
#let princeton-orange = rgb("#E77500")


// poster content, function from `template.typ`
#poster[

= #emoji.computer Code Snippet Example

#codly(
  languages: codly-languages,
  zebra-fill: princeton-zebra-fill,
)
```python
from coffea.nanoevents import NanoAODSchema, NanoEventsFactory
from coffea.nanoevents.mapping import BufferCache
from numcodecs import Blosc


buffer_cache = BufferCache(
  cache={},
  codec=Blosc("zstd", clevel=1, shuffle=Blosc.BITSHUFFLE)
)

factory = NanoEventsFactory.from_root(
  {path: "Events"},
  schemaclass=NanoAODSchema,
  mode="virtual",
  buffer_cache=buffer_cache,
)
```

= #emoji.basket Other Cache Examples

Exemplary cache implementations using `zict` for in-memory caching with an LRU eviction policy and on-disk caching.

A cache is a key-value store that needs to fulfill the `MutableMapping[str, bytes]` interface. This means that the keys must be strings and the values must be bytes.

In the following there are examples for `inmemory`, `inmemory_lru`, and `ondisk` caches.

#codly(
  languages: codly-languages,
  zebra-fill: princeton-zebra-fill,
)
```python
from coffea.nanoevents import NanoAODSchema, NanoEventsFactory
from coffea.nanoevents.mapping import BufferCache
from numcodecs import Blosc
import zict

inmemory = {}
inmemory_lru = zict.LRU(
  n=100 * (1024 ** 2), # 100 MiB max size
  d={}, 
  weight=lambda k, v: len(v),
)
ondisk = zict.File("cache_dir")


buffer_cache = BufferCache(
  cache=inmemory, # or inmemory_lru, or ondisk
  codec=Blosc("zstd", clevel=1, shuffle=Blosc.BITSHUFFLE)
)
```

= #emoji.page Text Example

#lorem(900)


#clue(
  accent-color: princeton-orange,
  title: "Additional Information and Tips",
  icon: emoji.clip,
)[
    Checkout the new features and improvements of Coffea! \
    \
    If you're already a coffea user: `coffea v2026.4` (April 2026, CalVer) release (and newer) includes all of these improvements. \
    \
    Stay up-to-date and follow our projects on GitHub at #link("https://github.com/scikit-hep")[https://github.com/scikit-hep].
]

]