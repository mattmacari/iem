"""
Samples the SNET feed, so we can complain about sites that have bad clocks!
"""

from twisted.internet import reactor
from twisted.application import service, internet
from twisted.python import log
import pyiem.nwnformat as nwnformat
import re
import datetime

from nwnserver import hubclient

from pyiem.network import Table as NetworkTable
nt = NetworkTable(("KCCI", "KIMT", "KELO"))
id2nwsli = {}
for sid in nt.sts.keys():
    if nt.sts[sid]['nwn_id'] is not None:
        id2nwsli[int(nt.sts[sid]['nwn_id'])] = sid


class NWNClientFactory(hubclient.HubClientProtocolBaseFactory):
    maxDelay = 60.0
    factor = 1.0
    initialDelay = 60.0

    def processData(self, data):
        reactor.callLater(0, ingestData, data)


db = {}


def ingestData(data):
    if data is None or data == "":
        return

    tokens = re.split("\s+", data)
    if len(tokens) != 14:
        return

    siteID = tokens[1]
    if tokens[2] != "Min" and tokens[2] != "Max":
        if siteID not in db:
            db[siteID] = nwnformat.nwnformat()
        db[siteID].raw = tokens
        db[siteID].parseLineRT(tokens)


def saveData():
    log.msg("saveData() called...")
    out = open('times.txt', 'w')
    for key in db.keys():
        sid = int(key)
        now = datetime.datetime.now()
        if sid in id2nwsli:
            t = db[key].raw[2]
            d = db[key].raw[3]
            ts = datetime.datetime.strptime(t + " " + d, "%H:%M %m/%d/%y")
            delta = (now - ts).days * 86400.0 + (now - ts).seconds
            out.write("%s|%s|%.0f\n" % (id2nwsli[sid],
                                        nt.sts[id2nwsli[sid]]["name"], delta))
        else:
            log.msg("Unknown site ID of: %s" % (sid,))

    out.close()
    reactor.stop()

application = service.Application("PythonHub")
serviceCollection = service.IServiceCollection(application)

nwn = NWNClientFactory('sall999', 'sall999')

cli = internet.TCPClient('129.186.185.33', 14996, nwn)
cli.setServiceParent(serviceCollection)
reactor.callLater(120, saveData)
