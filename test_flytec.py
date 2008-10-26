import logging

import flytec
import flytec_fuse

logging.basicConfig(level=logging.INFO)
io = flytec.POSIXSerialIO('/dev/ttyUSB0')
f = flytec.Flytec(io)
rd = flytec_fuse.RoutesDirentry(f)
print rd.read(8192, 0)
