#!/usr/bin/env python3
import os
import re

ROOT = r"C:\Users\TheOgre\Documents\coding\sharkiqdecomp\ghidra\sharkiq\decomp2"  # adjust to your path

url_pattern = re.compile(rb"https://[a-zA-Z0-9._\-/:%?=]+")
hosts = set()
samples = {}

for dirpath, _, filenames in os.walk(ROOT):
    for name in filenames:
        path = os.path.join(dirpath, name)
        try:
            with open(path, "rb") as f:
                data = f.read()
        except Exception:
            continue

        for m in url_pattern.finditer(data):
            url = m.group(0)
            # Normalize / store by host
            try:
                s = url.decode("utf-8", errors="ignore")
            except Exception:
                continue
            # crude host extraction
            host = s.split("/")[2] if "://" in s else s
            hosts.add(host)
            samples.setdefault(host, s)

print("Found hosts:")
for h in sorted(hosts):
    print("  ", h)

print("\nExample URLs per host:")
for h in sorted(samples.keys()):
    print("  ", h, "->", samples[h][:120])
