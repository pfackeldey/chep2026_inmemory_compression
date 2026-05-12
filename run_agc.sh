#!/usr/bin/env bash

action() {
  # --- 1. Modern coffea 2024+ (buffer-cache based) ---
  for cache in "inmemory" "inmemory_lru_100MiB" "inmemory_lru_500MiB" "ondisk"
  do
    for codec in "none" "blosc"
    do
      for ((entry_stop=100000; entry_stop<=1000000; entry_stop+=50000))
      do
        echo "Running: pixi run python benchmarks/agc.py $cache $codec $entry_stop"
        pixi run python benchmarks/agc.py $cache $codec $entry_stop
      done
    done
  done

  # --- 2. Modern coffea vanilla ---
  for ((entry_stop=100000; entry_stop<=1000000; entry_stop+=50000))
  do
    echo "Running: pixi run python benchmarks/agc.py nocache none $entry_stop"
    pixi run python benchmarks/agc.py nocache none "$entry_stop"
  done

  # --- 2. Legacy coffea 0.7.x (no buffer cache support) ---
  cd benchmarks/agc07
  for ((entry_stop=100000; entry_stop<=1000000; entry_stop+=50000))
  do
    echo "Running: pixi run agc07 no_buffer_cache $entry_stop"
    pixi run agc07 no_buffer_cache "$entry_stop"
  done

  cd -

  echo "Make plots..."
  pixi run python benchmarks/agc_result_plots.py
}
action "$@"
