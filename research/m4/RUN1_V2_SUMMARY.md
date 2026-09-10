# M4 Run 1 — v2 moving-block-bootstrap inference  (2026-09-10)

Bootstrap: moving-block, B = 400, block ≥ H bars, (block×session)-stratified.

Re-validated the 305 Run-1 FDR-significant cells; the other 12,598 keep their Run-1 analytic p for the combined FDR.

## Gate counts

| gate | Run 1 (analytic) | v2 (block bootstrap) |
|---|---|---|
| FDR-significant | 1689 | 1613 |
| + stable | 619 | 522 |
| + shift-robust ⇒ A=YES | 305 | 215 |

**A=YES survival:** 215 of 305 Run-1 A=YES cells survive the block bootstrap; 90 drop; 0 newly qualify.

### surviving A=YES by state class
cls
EVENT       87
MARKET      84
TEMPORAL    44

### surviving A=YES: directional vs non-directional
directional: 11   non-directional: 204

### surviving DIRECTIONAL A=YES cells
state anchor  bucket  H       metric    effect  effect_v2    se_v2     p_v2        b1        b2        b3        b4  cochran_p_v2    I2_v2  shift_delta  n_S  events_per_year
   m1     A2       2  2     race_1_1 -0.067405  -0.066061 0.025909 0.010779 -0.086710 -0.008776 -0.074211 -0.101169      0.437003 0.000000     0.032746 1106             62.6
   m1     A2       0 16 location_dir  0.273570   0.273570 0.093562 0.003456  0.289594  0.194776  0.665446  0.297814      0.752642 0.000000     0.241684 1493             84.5
   m1     A3       0 16 location_dir  0.250992   0.250992 0.085754 0.003424  0.339215  0.248949 -0.079454  0.304507      0.576069 0.000000     0.120787 3354            189.9
   m1     A3       1 16 location_dir -0.251339  -0.251339 0.083844 0.002720 -0.317469 -0.199975 -0.025826 -0.355778      0.774317 0.000000     0.063219 2411            136.5
   m1     A3       0 32 location_dir  0.422981   0.422981 0.116936 0.000298  0.437696  0.463700  0.151823  0.433535      0.899474 0.000000     0.095820 3354            189.9
   m1     A3       0 96 location_dir  0.848349   0.848349 0.193056 0.000011  0.441032  1.028156  1.416995  0.719904      0.433459 0.000000     0.113472 3354            189.9
   m3     A3       0 32 location_dir  0.383274   0.383274 0.119810 0.001379  0.623199  0.346838  0.077024  0.126760      0.502087 0.000000     0.087698 2841            160.8
   m4     A2       2  4     race_1_2  0.063388   0.064046      NaN      NaN  0.076765  0.062874  0.063656  0.031568      0.966892 0.000000     0.022071  556             31.5
   m4     A2       2  8     race_1_2  0.074172   0.075805 0.020974 0.000301  0.072973  0.095655  0.102404 -0.035991      0.259450 0.253493     0.078439  556             31.5
   m4     A3       4 32 location_dir  0.480859   0.480859 0.146110 0.000998  0.502445  0.644824  1.051700  0.078280      0.230270 0.303283     0.153198 1798            101.8
   m5     A2       1 32 location_dir  0.376085   0.376085 0.130623 0.003987  0.597097  0.250595  0.635336 -0.046952      0.371379 0.042847     0.202727 1362             77.1

## PRIMARY LEAD — M1 LOW-vol regime × A3 new-1-day-extreme → location_dir

 H   effect  effect_v2    se_v2     p_v2       b1       b2        b3       b4  cochran_p_v2  I2_v2 loo_ok_v2  shift_delta  fdr_sig_v2  stability_ok_v2  A_v2  n_S  events_per_year
 2 0.046845        NaN      NaN      NaN      NaN      NaN       NaN      NaN           NaN    NaN       NaN     1.009783       False            False False 3354            189.9
 4 0.057751        NaN      NaN      NaN      NaN      NaN       NaN      NaN           NaN    NaN       NaN     0.853515       False            False False 3354            189.9
 8 0.121840        NaN      NaN      NaN      NaN      NaN       NaN      NaN           NaN    NaN       NaN     0.262307       False             True False 3354            189.9
16 0.250992   0.250992 0.085754 0.003424 0.339215 0.248949 -0.079454 0.304507      0.576069    0.0      True     0.120787        True             True  True 3354            189.9
32 0.422981   0.422981 0.116936 0.000298 0.437696 0.463700  0.151823 0.433535      0.899474    0.0      True     0.095820        True             True  True 3354            189.9
96 0.848349   0.848349 0.193056 0.000011 0.441032 1.028156  1.416995 0.719904      0.433459    0.0      True     0.113472        True             True  True 3354            189.9

**Primary lead: 3 of 6 horizon-cells survive as A=YES under the block bootstrap.**
