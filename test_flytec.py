import logging

import flytec
import flytecfs

logging.basicConfig(level=logging.INFO)
io = flytec.POSIXSerialIO('/dev/ttyUSB0')
f = flytec.Flytec(io)
rd = flytecfs.RoutesFile(f)
print rd.read(8192, 0)
