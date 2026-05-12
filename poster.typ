#import "template.typ": *

#import "@preview/cetz:0.4.0": canvas, draw
#import "@preview/cetz-plot:0.1.2": plot
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
#set text(size: 34pt)
#show link: set text(fill: blue)
#show link: underline

#let princeton-zebra-fill = rgb("#a0a0a01a")
#let princeton-orange = rgb("#E77500")


// poster content, function from `template.typ`
#poster[

= Memory Limits Kill Your Jobs

Chunk too big #sym.arrow.r crash. Chunk too small #sym.arrow.r slow.

Limited memory forces tiny chunks, causing:
- Task scheduling overhead
- Inefficient use of vectorized kernels
- Python overhead

*Reduced memory footprint #sym.arrow.r more robust & faster analysis*


= How Awkward Arrays Are Stored in Memory

Nested data (e.g. per-event jet lists) are stored as flat 1D buffers:
- *Offsets:* where each event starts/ends
- *Values:* all data flattened into one array

100k events #sym.arrow.r just 2 contiguous buffers (not 100k Python lists!).

Each buffer has a *unique key*.
This maps naturally to a key-value store for compression and lazy lookup.

#align(center)[
  #grid(
    columns: (auto, auto),
    gutter: 1.5em,
    row-gutter: 1.5em,

    // Stage 1: Logical user view
    align(horizon + right)[
      *User View*
    ],
    align(horizon + left)[
      #box(
        width: 92%,
        stroke: gray,
        inset: 1em,
        radius: 0.5em,
        fill: princeton-zebra-fill,
        align(left)[
          === Jet-momenta for variable number of Jets
          #grid(
            columns: 2,
            gutter: 0.75em,
            align(right)[Event 0:],
            align(left)[*[45.2, 32.1, 12.5]*],
            align(right)[Event 1:],
            align(left)[*[67.8]*],
            align(right)[Event 2:],
            align(left)[*[23.0, 91.4]*],
          )
        ]
      )
    ],

    // Stage 2: Buffers
    align(horizon + right)[
      *1D Buffers*
    ],
    align(horizon + left)[
      #box(
        width: 92%,
        stroke: gray,
        inset: 1em,
        radius: 0.5em,
        fill: princeton-zebra-fill,
        align(left)[
          === In-memory Layout of Awkward Arrays
          #grid(
            columns: 2,
            gutter: 0.75em,
            align(right)[Offsets:],
            align(left)[*[0, 3, 4, 6]*],
            align(right)[Values:],
            align(left)[*[45.2, 32.1, 12.5, 67.8, 23.0, 91.4]*],
          )
        ]
      )
    ],

    // Stage 3: KV store
    align(horizon + right)[
      *Key-Value Store* \ #box(fill: princeton-orange, inset: 0.3em, radius: 0.2em)[#text(white)[*NEW!*]]
    ],
    align(horizon + left)[
      #box(
        width: 92%,
        stroke: orange,
        inset: 1em,
        radius: 0.5em,
        fill: rgb("#e7740029"), // princeton-orange with alpha
        align(left)[
          *Key-Value Cache Store for 1D Buffers* \
          #grid(
            columns: 3,
            gutter: 0.75em,
            align(right)[#raw("offsets/jets/pt")],
            align(center)[ #sym.arrow.r ],
            align(left)[Offsets],
            align(right)[#raw("data/jets/pt")],
            align(center)[ #sym.arrow.r ],
            align(left)[Values],
          )
        ]
      )
    ],
  )
]

*Benefits of a Key-Value Store for Buffers:*
- Full control over caching strategy
- Only accessed buffers are loaded into the key-value store (VirtualArrays)
- Transparent to users


= Solution: `BufferCache` for Awkward Arrays

New in coffea: plug any key-value store (`BufferCache`) underneath your arrays.

#codly(
  languages: codly-languages,
  zebra-fill: princeton-zebra-fill,
  highlights: (
    (line: 9, start: 3, end: 27, fill: princeton-orange),
  ),
)
```python
from coffea.nanoevents import NanoAODSchema, NanoEventsFactory
from coffea.nanoevents.mapping import BufferCache

buffer_cache = BufferCache(...)

factory = NanoEventsFactory.from_root(
  {path: "Events"},
  mode="virtual",
  buffer_cache=buffer_cache,
)
```

Three strategies below:

=== 1. In-Memory Compression

Compress buffers before caching. Decompress only on access → larger chunks, same memory limit.

*Example with Blosc:*

#codly(
  languages: codly-languages,
  zebra-fill: princeton-zebra-fill,
)
```python
from coffea.nanoevents.mapping import BufferCache
from numcodecs import Blosc

buffer_cache = BufferCache(
  cache={},
  codec=Blosc("zstd", clevel=1, shuffle=Blosc.BITSHUFFLE)
)
```

=== 2. On-Disk Caching

Spill buffers to disk. Bypasses memory limits entirely — at the cost of I/O latency.

#codly(
  languages: codly-languages,
  zebra-fill: princeton-zebra-fill,
)
```python
from coffea.nanoevents.mapping import BufferCache
from numcodecs import Blosc; import zict

buffer_cache = BufferCache(
  cache=zict.File("cache_dir"),
  codec=Blosc("zstd", clevel=1, shuffle=Blosc.BITSHUFFLE)
)
```

=== 3. Custom / Tiered Caches

Any `MutableMapping[str, bytes]` works — e.g. tiered caches that spill to disk once a memory threshold is reached, using `zict.LRU` or similar.


= Benchmarks

Comparing memory use for a typical coffea analysis, using the #emph[Analysis Grand Challenge] with a CMS open data t#overline[t] NanoAOD sample:

- No cache (default): `coffea 0.7` and `coffea 2026.4`
- In-memory (`Blosc`)
- On-disk (`zict.File`, SSD #sym.approx$10$ GB/s read speed)
- Tiered LRU (`zict.LRU`)

#figure(image("benchmarks/plots/peak_rss_vs_entry_stop.pdf", width: 100%, height: auto))

*Results*
- Peak RSS *reduced by up to #sym.approx$2$#sym.times* with on-disk caching
- In-memory compression also reduces peak RSS vs default, especially at higher chunk sizes
- Runtime overhead #sym.approx$1..30\%$ (depends on cache strategy and chunk size)
  - Mitigated by larger chunks + codec tuning
  - On-disk performance is _highly sensitive to disk bandwidth_\ *#sym.arrow.r understand your setup!*


\
#set text(size: 40pt)
*#sym.arrow.r Try `coffea>=2026.4` if memory limits slow you down!*

]