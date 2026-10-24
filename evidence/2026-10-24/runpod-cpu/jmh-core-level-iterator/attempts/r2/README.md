# Complete CPU core A/B/A/B

All15cases,3forks/case,500warmup/10measurement; normalized64-command batch means. No outliers removed.

|Case|Params|A mean us|B mean us|Pair1 B/A|Pair2 B/A|Combined B/A|
|---|---|---:|---:|---:|---:|---:|
|MATCH|{'initialPriceLevels': '1', 'tradesPerCommand': '1'}|0.388877|0.366226|1.051|0.860|0.942|
|MATCH|{'initialPriceLevels': '1', 'tradesPerCommand': '10'}|0.670544|0.645535|0.948|0.978|0.963|
|MATCH|{'initialPriceLevels': '1', 'tradesPerCommand': '100'}|5.473930|1.933905|0.368|0.339|0.353|
|MATCH|{'initialPriceLevels': '100', 'tradesPerCommand': '1'}|0.415524|0.351068|0.625|1.143|0.845|
|MATCH|{'initialPriceLevels': '100', 'tradesPerCommand': '10'}|0.777928|0.840541|1.267|0.888|1.080|
|MATCH|{'initialPriceLevels': '100', 'tradesPerCommand': '100'}|3.433841|2.683192|0.766|0.797|0.781|
|MATCH|{'initialPriceLevels': '10000', 'tradesPerCommand': '1'}|0.245296|0.238884|0.941|1.009|0.974|
|MATCH|{'initialPriceLevels': '10000', 'tradesPerCommand': '10'}|0.761338|0.763059|0.998|1.007|1.002|
|MATCH|{'initialPriceLevels': '10000', 'tradesPerCommand': '100'}|4.955689|5.037327|0.994|1.039|1.016|
|PLACE|{'action': 'PLACE', 'initialPriceLevels': '1'}|0.298494|0.306465|1.012|1.042|1.027|
|PLACE|{'action': 'PLACE', 'initialPriceLevels': '100'}|0.285266|0.265141|0.899|0.955|0.929|
|PLACE|{'action': 'PLACE', 'initialPriceLevels': '10000'}|0.341365|0.337258|0.972|1.004|0.988|
|CANCEL|{'action': 'CANCEL', 'initialPriceLevels': '1'}|0.291198|0.249057|0.655|1.028|0.855|
|CANCEL|{'action': 'CANCEL', 'initialPriceLevels': '100'}|0.257279|0.217810|0.716|1.001|0.847|
|CANCEL|{'action': 'CANCEL', 'initialPriceLevels': '10000'}|0.459354|0.462307|0.993|1.021|1.006|

B/A<1 means lower measured time. See [all fork means and ranges](comparison.json). These finite descriptive comparisons do not establish individual-order p99, significance, sustained new-command rate or replicated-path improvement. The capacity workload uses one repeatedly partial maker and needs a separate comparison.
