Workloads: retired dynamic instruction mix (measured on the golden ISS)

| workload | retired | alu % | shift % | compare % | load % | store % | branch % | jal % | jalr % | taken/not-taken |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| checksum | 196 | 50.5 | 16.3 | 8.2 | 8.2 | 8.7 | 8.2 | 0.0 | 0.0 | 15/1 |
| memcpy | 86 | 33.7 | 0.0 | 0.0 | 27.9 | 29.1 | 9.3 | 0.0 | 0.0 | 7/1 |
| softmul | 60 | 31.7 | 33.3 | 0.0 | 0.0 | 1.7 | 33.3 | 0.0 | 0.0 | 13/7 |
| sort | 452 | 32.5 | 1.8 | 10.8 | 23.5 | 6.4 | 25.0 | 0.0 | 0.0 | 90/23 |
| popcount | 1324 | 60.0 | 19.3 | 0.0 | 0.6 | 0.1 | 19.9 | 0.0 | 0.0 | 255/9 |
