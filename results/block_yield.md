Defect density and clustering fixed by the yield data of [1] (tools/block_yield.py)

| structure | T | functional | yield | 95 % CI | Poisson d (ppm/T) | 95 % CI |
|:--|--:|--:|--:|:--|--:|:--|
| transistor | 1 | n/a | 99.92 % | -- | 800 | -- |
| inverter | 2 | 898/900 | 99.78 % | 99.20-99.97 % | 1112 | 135-4018 |
| 8-bit register | 144 | 159/224 | 70.98 % | 64.56-76.84 % | 2380 | 1830-3038 |
| 64-bit register | 1152 | 2/28 | 7.14 % | 0.88-23.50 % | 2291 | 1257-4111 |

Negative-binomial fit to the two register sizes: d = 2394 ppm/T (95 % 1896-3260), alpha = 30 (95 % lower bound 1.3, upper unbounded).  Poisson-only fit: d = 2363 ppm/T, likelihood-ratio statistic 0.018 (p = 0.89): the data do not distinguish clustering from Poisson.

Profile-likelihood p-value of each break-even alpha* (Table XIII): delay budget, 1 kHz, die (alpha* = 5.0): p = 0.56, delay budget, fmax, die (alpha* = 3.7): p = 0.43, delay budget, 1 kHz, area (alpha* = 3.1): p = 0.36, cascade, die (alpha* = 2.1): p = 0.20, cascade, area (alpha* = 0.9): p = 0.02

Per-die envelope selection under the fitted parameters:

| point | d (ppm/T) | alpha | delay budget, 1 kHz | delay budget, fmax | cascade |
|:--|--:|--:|:--|:--|:--|
| fit | 2394 | 30.3 | W=1 ripple | W=1 ripple | W=1 ripple |
| alpha lower 95 % | 2954 | 1.3 | W=32 ripple | W=16 prefix | W=16 prefix |
| 800 ppm/T, fitted alpha | 800 | 30.3 | W=1 ripple | W=1 ripple | W=1 ripple |

Die yield under the fitted model: 5931 T: 8.8e-06, 10474 T: 1.2e-08, 15500 T: 3.0e-11, 27195 T: 8.2e-16
