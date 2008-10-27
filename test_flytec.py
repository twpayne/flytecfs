import logging

import flytec
import flytecfs
import flytecproxy

logging.basicConfig(level=logging.INFO)
io = flytec.POSIXSerialIO('/dev/ttyUSB1')
f = flytec.Flytec(io)
fp = flytecproxy.FlytecProxy(f)
rd = flytecfs.RoutesFile(fp)
file = open('routes.gpx', 'w')
file.write(rd.read(1024 * 1024, 0))
file.close()
rd = flytecfs.TracklogsZipFile(fp)
file = open('tracks.zip', 'w')
file.write(rd.read(1024 * 1024, 0))
file.close()
