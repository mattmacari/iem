"""x-hour temp change"""
import datetime
from collections import OrderedDict

import psycopg2
from pandas.io.sql import read_sql
from pyiem.network import Table as NetworkTable
from pyiem.util import get_autoplot_context

MDICT = {'warm': 'Temperature Rise',
         'cool': 'Temperature Drop'}
MDICT2 = OrderedDict([
         ('all', 'No Month/Time Limit'),
         ('spring', 'Spring (MAM)'),
         ('fall', 'Fall (SON)'),
         ('winter', 'Winter (DJF)'),
         ('summer', 'Summer (JJA)'),
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


def get_description():
    """ Return a dict describing how to call this plotter """
    desc = dict()
    desc['data'] = True
    desc['cache'] = 86400
    desc['description'] = """This chart presents the largest changes in
    temperature over a given number of hours.  This is based on available
    hourly temperature reports.  It also requires an exact match in time of
    day between two observations.
    """
    desc['arguments'] = [
        dict(type='zstation', name='zstation', default='DSM',
             label='Select Station:', network='IA_ASOS'),
        dict(type='int', name='hours', label='Number of Hours:',
             default=24),
        dict(type='select', name='month', default='all',
             label='Month Limiter', options=MDICT2),
        dict(type='select', name='dir', default='warm',
             label='Direction:', options=MDICT),
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
    hours = ctx['hours']
    mydir = ctx['dir']
    month = ctx['month']

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
    else:
        ts = datetime.datetime.strptime("2000-"+month+"-01", '%Y-%b-%d')
        # make sure it is length two for the trick below in SQL
        months = [ts.month, 999]

    nt = NetworkTable(network)
    tzname = nt.sts[station]['tzname']

    # backwards intuitive
    sortdir = "ASC" if mydir == 'warm' else 'DESC'
    df = read_sql("""
    WITH data as (
        SELECT valid at time zone %s as valid, tmpf from alldata
        where station = %s and tmpf between -100 and 150
        and extract(month from valid) in %s),
    doffset as (
        SELECT valid - '%s hours'::interval as valid, tmpf from data),
    agg as (
        SELECT d.valid, d.tmpf as tmpf1, o.tmpf as tmpf2
        from data d JOIN doffset o on (d.valid = o.valid))
    SELECT valid as valid1, valid + '%s hours'::interval as valid2,
    tmpf1, tmpf2 from agg
    ORDER by (tmpf1 - tmpf2) """ + sortdir + """ LIMIT 50
    """, pgconn, params=(tzname, station, tuple(months),
                         hours, hours), index_col=None)
    df['diff'] = (df['tmpf1'] - df['tmpf2']).abs()

    if len(df.index) == 0:
        return "No database entries found for station, sorry!"

    fig = plt.figure()
    ax = plt.axes([0.55, 0.1, 0.4, 0.8])

    fig.text(0.5, 0.95, ('[%s] %s Top 10 %s\n'
                         'Over %s Hour Period (%s-%s) [%s]'
                         ) % (station, nt.sts[station]['name'], MDICT[mydir],
                              hours, nt.sts[station]['archive_begin'].year,
                              datetime.date.today().year, MDICT2[month]),
             ha='center', va='center')

    labels = []
    for i in range(10):
        row = df.iloc[i]
        ax.barh(i+1, row['diff'], align='center')
        sts = row['valid1']
        ets = row['valid2']
        labels.append(("%.0f to %.0f -> %.0f\n%s - %s"
                       ) % (row['tmpf1'], row['tmpf2'],
                            row['diff'],
                            sts.strftime("%-d %b %Y %I:%M %p"),
                            ets.strftime("%-d %b %Y %I:%M %p")))
    ax.set_yticks(range(1, 11))
    ax.set_yticklabels(labels)
    ax.set_ylim(10.5, 0.5)
    ax.grid(True)
    return fig, df


if __name__ == '__main__':
    plotter(dict(station='DSM', year=2009, month=1, network='IA_ASOS'))
