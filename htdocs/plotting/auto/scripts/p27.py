"""
  Fall Minimum by Date
"""
import psycopg2
from pandas.io.sql import read_sql
import numpy as np
import datetime
from pyiem.network import Table as NetworkTable
from pyiem.util import get_autoplot_context


def get_description():
    """ Return a dict describing how to call this plotter """
    d = dict()
    d['data'] = True
    d['description'] = """This chart presents the date of the first fall
    (date after 1 July) temperature below threshold 1 and then the number of
    days after that date until threshold 2 was reached."""
    d['arguments'] = [
        dict(type='station', name='station', default='IA0200',
             label='Select Station:', network='IACLIMATE'),
        dict(type='int', name='t1', default=32,
             label='Temperature Threshold 1:'),
        dict(type='int', name='t2', default=29,
             label='Temperature Threshold 2:'),
    ]
    return d


def plotter(fdict):
    """ Go """
    import matplotlib
    matplotlib.use('agg')
    import matplotlib.pyplot as plt
    pgconn = psycopg2.connect(database='coop', host='iemdb', user='nobody')
    ctx = get_autoplot_context(fdict, get_description())

    station = ctx['station']
    t1 = ctx['t1']
    t2 = ctx['t2']

    table = "alldata_%s" % (station[:2],)
    nt = NetworkTable("%sCLIMATE" % (station[:2],))

    df = read_sql("""
        SELECT year,
        min(low) as min_low,
        min(case when low < %s then extract(doy from day)
            else 999 end) as t1_doy,
        min(case when low < %s then extract(doy from day)
            else 999 end) as t2_doy
        from """+table+""" where station = %s and month > 6
        GROUP by year ORDER by year ASC
    """, pgconn, params=(t1, t2, station), index_col='year')
    df = df[df['t2_doy'] < 400]

    doy = np.array(df['t1_doy'], 'i')
    doy2 = np.array(df['t2_doy'], 'i')

    sts = datetime.datetime(2000, 1, 1)
    xticks = []
    xticklabels = []
    for i in range(min(doy), max(doy2)+1):
        ts = sts + datetime.timedelta(days=i)
        if ts.day in [1, 8, 15, 22]:
            xticks.append(i)
            fmt = "%b %-d" if ts.day == 1 else "%-d"
            xticklabels.append(ts.strftime(fmt))

    (fig, ax) = plt.subplots(1, 1)
    ax.set_xticks(xticks)
    ax.set_xticklabels(xticklabels)
    ax.scatter(doy, doy2-doy)

    for x in xticks:
        ax.plot((x-100, x), (100, 0), ':', c=('#000000'))

    ax.set_ylim(-1, max(doy2-doy)+4)
    ax.set_xlim(min(doy)-4, max(doy)+4)

    ax.set_title("[%s] %s\nFirst Fall Temperature Occurences" % (
                                            station, nt.sts[station]['name']))
    ax.set_ylabel("Days until first sub %s$^{\circ}\mathrm{F}$" % (t2,))
    ax.set_xlabel("First day of sub %s$^{\circ}\mathrm{F}$" % (t1,))

    ax.grid(True)

    return fig, df


if __name__ == '__main__':
    plotter(dict())
