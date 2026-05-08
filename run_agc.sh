#!/usr/bin/env bash

action() {
  for cache in "inmemory" "inmemory_lru_100MiB" "inmemory_lru_500MiB" "ondisk"
  do
    for codec in "none" "blosc"
    do
      for ((entry_stop=100000; entry_stop<=1000000; entry_stop+=50000)) # from 100k to 1M in steps of 50k
      do 
        echo "Running: pixi run python benchmarks/agc.py $cache $codec $entry_stop"
        pixi run python benchmarks/agc.py $cache $codec $entry_stop
      done
    done
  done


  echo "Make plots..."
  pixi run python benchmarks/agc_result_plots.py
}
action "$@"
