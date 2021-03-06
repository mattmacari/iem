"""METAR frequency"""
import calendar
import datetime
from collections import OrderedDict

import psycopg2
from pandas.io.sql import read_sql
from pyiem.network import Table as NetworkTable
from pyiem.util import get_autoplot_context

PDICT = OrderedDict([
        ('TS', 'Thunder (TS)'),
        ('-SN', 'Light Snow (-SN)'),
        ('PSN', 'Heavy Snow (+SN)'),  # +SN causes CGI issues
        ('FZFG', 'Freezing Fog (FZFG)'),
        ('FG', 'Fog (FG)'),
        ('BLSN', 'Blowing Snow (BLSN)')])


def get_description():
    """ Return a dict describing how to call this plotter """
    desc = dict()
    desc['data'] = True
    desc['cache'] = 86400
    desc['description'] = """This chart totals the number of distinct calendar
    days per month that a given present weather condition is reported within
    the METAR data feed.  The calendar day is computed for the local time zone
    of the reporting station.
    """
    desc['arguments'] = [
        dict(type='zstation', name='zstation', default='DSM',
             label='Select Station:', network='IA_ASOS'),
        dict(type='year', name="year", label='Year to Highlight:',
             default=datetime.date.today().year, min=1973),
        dict(type='select', name='var', default='FG',
             label='Present Weather Option:', options=PDICT),
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
    year = ctx['year']
    pweather = ctx['var']
    if pweather == 'PSN':
        pweather = "+SN"
        PDICT['+SN'] = PDICT['PSN']

    nt = NetworkTable(network)
    tzname = nt.sts[station]['tzname']
    syear = max([1973, nt.sts[station]['archive_begin'].year])
    df = read_sql("""
    WITH data as (
        SELECT distinct date(valid at time zone %s) from alldata
        where station = %s and presentwx LIKE '%%""" + pweather + """%%'
        and valid > '1973-01-01' and report_type = 2)

    SELECT extract(year from date)::int as year,
    extract(month from date)::int as month,
    count(*) from data GROUP by year, month ORDER by year, month
    """, pgconn, params=(tzname, station), index_col=None)

    if len(df.index) == 0:
        return "No database entries found for station, sorry!"
    (fig, ax) = plt.subplots(1, 1)
    ax.set_title(("[%s] %s %s Events\n"
                  "(%s-%s) Distinct Calendar Days with '%s' Reported"
                  ) % (station, nt.sts[station]['name'], PDICT[pweather],
                       syear, datetime.date.today().year, pweather))
    df2 = df[df['year'] == year]
    if len(df2.index) > 0:
        ax.bar(df2['month'].values - 0.2, df2['count'].values,
               width=0.4, fc='r', ec='r', label='%s' % (year,))
    df2 = df.groupby('month').sum()
    years = (datetime.date.today().year - syear) + 1
    yvals = df2['count'] / years
    ax.bar(df2.index.values + 0.2, yvals, width=0.4, fc='b', ec='b',
           label='Avg')
    for x, y in zip(df2.index.values, yvals):
        ax.text(x, y + 0.2, "%.1f" % (y,))
    ax.set_xlim(0.5, 12.5)
    ax.set_xticklabels(calendar.month_abbr[1:])
    ax.set_xticks(range(1, 13))
    ax.set_ylabel("Days Per Month")
    ax.set_ylim(top=(ax.get_ylim()[1] + 2))
    ax.legend(loc='best')
    ax.grid(True)

    return fig, df


if __name__ == '__main__':
    plotter(dict(zstation='ALO', year=2017, var='FG', network='IA_ASOS'))
