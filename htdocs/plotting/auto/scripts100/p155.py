"""Top 10"""
import datetime
from collections import OrderedDict

import psycopg2
from pyiem.network import Table as NetworkTable
from pyiem.util import get_autoplot_context
from pandas.io.sql import read_sql

MDICT = OrderedDict([
         ('all', 'No Month/Time Limit'),
         ('spring', 'Spring (MAM)'),
         ('fall', 'Fall (SON)'),
         ('winter', 'Winter (DJF)'),
         ('summer', 'Summer (JJA)'),
         ('octmar', 'October thru March'),
         ('jan', 'January'),
         ('feb', 'February'),
         ('mar', 'March'),
         ('apr', 'April'),
         ('may', 'May'),
         ('jun', 'June'),
         ('jul', 'July'),
         ('aug', 'August'),
         ('sep', 'September'),
         ('oct', 'October'),
         ('nov', 'November'),
         ('dec', 'December')])

METRICS = OrderedDict([
    ('max_p01i', 'Max Hourly Precipitation'),
    ])


def get_description():
    """ Return a dict describing how to call this plotter """
    desc = dict()
    desc['data'] = True
    desc['cache'] = 86400
    desc['description'] = """Based on available hourly observation reports
    by METAR stations, this application presents the top 10 events for a
    given metric of your choice.
    """
    desc['arguments'] = [
        dict(type='zstation', name='zstation', default='AMW',
             network='IA_ASOS', label='Select Station:'),
        dict(type='select', name='var', default='max_p01i',
             label='Which Metric to Summarize', options=METRICS),
        dict(type='select', name='month', default='all',
             label='Month Limiter', options=MDICT),

    ]
    return desc


def plotter(fdict):
    """ Go """
    import matplotlib
    matplotlib.use('agg')
    import matplotlib.pyplot as plt
    pgconn = psycopg2.connect(database='asos', host='iemdb', user='nobody')
    ctx = get_autoplot_context(fdict, get_description())

    station = ctx['zstation']
    network = ctx['network']
    month = ctx['month']
    varname = ctx['var']

    nt = NetworkTable(network)

    if month == 'all':
        months = range(1, 13)
    elif month == 'fall':
        months = [9, 10, 11]
    elif month == 'winter':
        months = [12, 1, 2]
    elif month == 'spring':
        months = [3, 4, 5]
    elif month == 'summer':
        months = [6, 7, 8]
    elif month == 'octmar':
        months = [10, 11, 12, 1, 2, 3]
    else:
        ts = datetime.datetime.strptime("2000-"+month+"-01", '%Y-%b-%d')
        # make sure it is length two for the trick below in SQL
        months = [ts.month, 999]

    (agg, dbvar) = varname.split("_")
    sorder = 'DESC' if agg == 'max' else 'ASC'
    df = read_sql("""WITH data as (
        SELECT valid at time zone %s as v, p01i from alldata
        WHERE station = %s and
        extract(month from valid at time zone %s) in %s)
    SELECT v as valid, p01i from data
    ORDER by """ + dbvar + """ """ + sorder + """ NULLS LAST LIMIT 100
        """, pgconn, params=(nt.sts[station]['tzname'],
                             station, nt.sts[station]['tzname'],
                             tuple(months)),
                  index_col=None)
    if len(df.index) == 0:
        return 'Error, no results returned!'
    ylabels = []
    fmt = '%.2f' if varname in ['max_p01i', ] else '%.0f'
    hours = []
    y = []
    lastval = -99
    ranks = []
    currentrank = 0
    for _, row in df.iterrows():
        key = row['valid'].strftime("%Y%m%d%H")
        if key in hours:
            continue
        hours.append(key)
        y.append(row[dbvar])
        lbl = fmt % (row[dbvar], )
        lbl += " -- %s" % (row['valid'].strftime("%b %d, %Y %-I:%M %p"),)
        ylabels.append(lbl)
        if row[dbvar] != lastval:
            currentrank += 1
        ranks.append(currentrank)
        lastval = row[dbvar]
        if len(ylabels) == 10:
            break

    fig = plt.figure(figsize=(8, 6))
    ax = plt.axes([0.1, 0.1, 0.5, 0.8])
    ax.barh(range(10, 0, -1), y, ec='green', fc='green', height=0.8,
            align='center')
    ax2 = ax.twinx()
    ax2.set_ylim(0.5, 10.5)
    ax.set_ylim(0.5, 10.5)
    ax2.set_yticks(range(1, 11))
    ax.set_yticks(range(1, 11))
    ax.set_yticklabels(["#%s" % (x,) for x in ranks][::-1])
    ax2.set_yticklabels(ylabels[::-1])
    ax.grid(True, zorder=11)
    ax.set_xlabel(("Precipitation [inch]"
                   if varname in ['max_p01i'] else r"Temperature $^\circ$F"
                   ))
    ax.set_title(("%s [%s] Top 10 Events\n"
                  "%s (%s) "
                  "(%s-%s)"
                  ) % (nt.sts[station]['name'], station, METRICS[varname],
                       MDICT[month],
                       nt.sts[station]['archive_begin'].year,
                       datetime.datetime.now().year), size=12)

    fig.text(0.98, 0.03, "Timezone: %s" % (nt.sts[station]['tzname'],),
             ha='right')

    return fig, df


if __name__ == '__main__':
    plotter(dict())
