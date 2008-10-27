import logging

import flytec
import flytecfs
import flytecproxy

logging.basicConfig(level=logging.INFO)
io = flytec.POSIXSerialIO('/dev/ttyUSB0')
f = flytec.Flytec(io)
fp = flytecproxy.FlytecProxy(f)
rd = flytecfs.TracklogsZipFile(fp)
file = open('tracks.zip', 'w')
file.write(rd.read(1024 * 1024, 0))
file.close()
