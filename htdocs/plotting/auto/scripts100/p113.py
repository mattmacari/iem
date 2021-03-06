"""daily records"""
import datetime

import psycopg2
from pandas.io.sql import read_sql
from pyiem.network import Table as NetworkTable
from pyiem.util import get_autoplot_context

PDICT = {'maxmin': 'Daily Maximum / Minimums',
         'precip': 'Daily Maximum Precipitation',
         'range': 'Daily Maximum Range between High and Low',
         'means': 'Daily Average High and Lows'}


def get_description():
    """ Return a dict describing how to call this plotter """
    desc = dict()
    desc['data'] = True
    desc['report'] = True
    desc['description'] = """ """
    desc['arguments'] = [
        dict(type='station', name='station', default='IA2203',
             label='Select Station', network='IACLIMATE'),
        dict(type="select", name="var", default="maxmin", options=PDICT,
             label="Which variable?")
    ]
    return desc


def plotter(fdict):
    """ Go """
    import matplotlib
    matplotlib.use('agg')
    pgconn = psycopg2.connect(database='coop', host='iemdb', user='nobody')
    ctx = get_autoplot_context(fdict, get_description())
    station = ctx['station']
    varname = ctx['var']

    nt = NetworkTable("%sCLIMATE" % (station[:2], ))
    res = """\
# IEM Climodat https://mesonet.agron.iastate.edu/climodat/
# Report Generated: %s
# Climate Record: %s -> %s
# Site Information: [%s] %s
# Contact Information: Daryl Herzmann akrherz@iastate.edu 515.294.5978
""" % (datetime.date.today().strftime("%d %b %Y"),
       nt.sts[station]['archive_begin'].date(), datetime.date.today(), station,
       nt.sts[station]['name'])
    if varname == 'maxmin':
        res += """\
# DAILY RECORD HIGHS AND LOWS OCCURRING DURING %s-%s FOR STATION NUMBER  %s
     JAN     FEB     MAR     APR     MAY     JUN     JUL     AUG     SEP     OCT     NOV     DEC
 DY  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN
""" % (nt.sts[station]['archive_begin'].year, datetime.date.today().year,
       station)
    elif varname == 'means':
        res += """\
# DAILY MEAN HIGHS AND LOWS FOR STATION NUMBER  %s
     JAN     FEB     MAR     APR     MAY     JUN     JUL     AUG     SEP     OCT     NOV     DEC
 DY  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN
""" % (station, )
    elif varname == 'range':
        res += """\
# RECORD LARGEST AND SMALLEST DAILY RANGES (MAX-MIN) FOR STATION NUMBER  %s
     JAN     FEB     MAR     APR     MAY     JUN     JUL     AUG     SEP     OCT     NOV     DEC
 DY  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN  MX  MN
""" % (station, )
    else:
        res += """\
# DAILY MAXIMUM PRECIPITATION FOR STATION NUMBER %s
     JAN   FEB   MAR   APR   MAY   JUN   JUL   AUG   SEP   OCT   NOV   DEC
""" % (station, )

    df = read_sql("SELECT * from climate WHERE station = %s",
                  pgconn, params=(station, ), index_col='valid')

    bad = "  ****" if varname == 'precip' else ' *** ***'
    for day in range(1, 32):
        res += "%3i" % (day,)
        for mo in range(1, 13):
            try:
                ts = datetime.date(2000, mo, day)
                if ts not in df.index:
                    res += bad
                    continue
            except Exception as _:
                res += bad
                continue
            row = df.loc[ts]
            if (row['max_high'] is None or
                    row['min_low'] is None):
                res += bad
                continue
            if varname == 'maxmin':
                res += ("%4i%4i" % (row["max_high"], row["min_low"]))
            elif varname == 'range':
                res += ("%4i%4i" % (row["max_range"], row["min_range"]))
            elif varname == 'means':
                res += ("%4i%4i" % (row["high"], row["low"]))
            else:
                res += "%6.2f" % (row["max_precip"], )
        res += ("\n")

    return None, df, res


if __name__ == '__main__':
    plotter(dict())
