import logging

import flytec
import flytecfs
import flytecproxy

logging.basicConfig(level=logging.INFO)
io = flytec.POSIXSerialIO('/dev/ttyUSB1')
f = flytec.Flytec(io)
fp = flytecproxy.FlytecProxy(f)
rd = flytecfs.RoutesFile(fp)
print rd.read(8192, 0)
