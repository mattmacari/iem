import psycopg2
import numpy as np
import datetime
import pytz
from pandas.io.sql import read_sql
from pyiem.network import Table as NetworkTable
from pyiem.util import get_autoplot_context


def get_description():
    """ Return a dict describing how to call this plotter """
    d = dict()
    d['data'] = True
    d['cache'] = 86400
    d['description'] = """This chart summarizes Flight Category by hour
    and day of a given month.  In the case of multiple observations for a
    given hour, the worst category is plotted.

<table class="table table-condensed table-bordered">
<thead><tr><th>code</th><th>Label</th><th>Description</th></tr></thead>
<tbody>
<tr><td>Unknown</td><td>Unknown</td><td>No report or missing visibility for
that hour</td></tr>
<tr><td>VFR</td><td>Visual Flight Rules</td><td>
Ceiling >3000' AGL and visibility >5 statutes miles (green)</td></tr>
<tr><td>MVFR</td><td>Marginal Visual Flight Rules</td><td>
1000-3000' ceilings and/or 3-5 statute miles, inclusive (blue)</td></tr>
<tr><td>IFR</td><td>Instrument Fight Rules</td><td>
500 - <1000' ceilings and/or 1 to <3 statute miles (red)</td></tr>
<tr><td>LIFR</td><td>Low Instrument Flight Rules</td><td>
< 500' AGL ceilings and/or < 1 mile (magenta)</td></tr>
</tbody>
</table>
</tbody>
</table>
    """
    today = datetime.date.today()
    d['arguments'] = [
        dict(type='zstation', name='zstation', default='DSM',
             label='Select Station:', network='IA_ASOS'),
        dict(type='month', name='month', label='Select Month:',
             default=today.month),
        dict(type='year', name='year', label='Select Year:',
             default=today.year, min=1970),
    ]
    return d


def plotter(fdict):
    """ Go """
    import matplotlib
    matplotlib.use('agg')
    import matplotlib.pyplot as plt
    import matplotlib.colors as mpcolors
    from matplotlib.patches import Rectangle
    pgconn = psycopg2.connect(database='asos', host='iemdb', user='nobody')
    ctx = get_autoplot_context(fdict, get_description())
    station = ctx['zstation']
    network = ctx['network']
    year = ctx['year']
    month = ctx['month']

    nt = NetworkTable(network)
    tzname = nt.sts[station]['tzname']
    tzinfo = pytz.timezone(tzname)

    # Figure out the 1rst and last of this month in the local time zone
    sts = datetime.datetime(year, month, 3, 0, 0)
    sts = sts.replace(tzinfo=pytz.utc)
    sts = sts.astimezone(tzinfo).replace(day=1, hour=0, minute=0)
    ets = (sts + datetime.timedelta(days=35)).replace(day=1)
    days = (ets-sts).days
    data = np.zeros((24, days))

    df = read_sql("""
    SELECT valid at time zone %s as ts,
    skyc1, skyc2, skyc3, skyc4, skyl1, skyl2, skyl3, skyl4,
    vsby
    from alldata where station = %s and valid BETWEEN %s and %s
    and vsby is not null and report_type = 2
    ORDER by valid ASC
    """, pgconn, params=(tzname, station, sts, ets), index_col=None)

    if len(df.index) == 0:
        return "No database entries found for station, sorry!"

    # 0 Unknown
    # 1 VFR: Ceiling >3000' AGL and visibility >5 statutes miles (green)
    # 2 MVFR: 1000-3000' and/or 3-5 statute miles, inclusive (blue)
    # 3 IFR: 500 - <1000' and/or 1 to <3 statute miles (red)
    # 4 LIFR: < 500' AGL and/or < 1 mile (magenta)
    lookup = {4: 'LIFR', 3: 'IFR', 2: 'MVFR', 1: 'VFR', 0: 'UNKNOWN'}
    conds = []
    for _, row in df.iterrows():
        x = row['ts'].day - 1
        y = row['ts'].hour
        val = 1
        level = 100000  # arb high number
        coverages = [row['skyc1'], row['skyc2'], row['skyc3'], row['skyc4']]
        if 'OVC' in coverages:
            idx = coverages.index('OVC')
            level = [row['skyl1'], row['skyl2'], row['skyl3'], row['skyl4']
                     ][idx]
        if level < 500 or row['vsby'] < 1:
            val = 4
        elif (level < 1000 and level >= 500) or row['vsby'] < 3:
            val = 3
        elif (level < 3000 and level >= 1000) or row['vsby'] < 5:
            val = 2
        elif level >= 3000 and row['vsby'] >= 5:
            val = 1
        else:
            val = 0
        data[y, x] = max(data[y, x], val)
        conds.append(lookup[val])
        # print row['ts'], y, x, val, data[y, x], level, row['vsby']

    df['flstatus'] = conds

    (fig, ax) = plt.subplots(1, 1, figsize=(8, 6))

    ax.set_axis_bgcolor('skyblue')

    ax.set_title(('[%s] %s %s Flight Category\n'
                  'based on Hourly METAR Cloud Amount/Level'
                  ' and Visibility Reports'
                  ) % (station, nt.sts[station]['name'],
                       sts.strftime("%b %Y")))

    colors = ['#EEEEEE', 'green', 'blue', 'red', 'magenta']
    cmap = mpcolors.ListedColormap(colors)
    norm = mpcolors.BoundaryNorm(boundaries=range(6), ncolors=5)
    ax.imshow(np.flipud(data), aspect='auto', extent=[0.5, days + 0.5, -0.5,
                                                      23.5],
              cmap=cmap, interpolation='nearest', norm=norm)
    ax.set_yticks(range(0, 24, 3))
    ax.set_yticklabels(['Mid', '3 AM', '6 AM', '9 AM', 'Noon',
                        '3 PM', '6 PM', '9 PM'])
    ax.set_xticks(range(1, days+1))
    ax.set_ylabel("Hour of Local Day (%s)" % (tzname, ))
    ax.set_xlabel("Day of %s" % (sts.strftime("%b %Y"),))

    rects = []
    for color in colors:
        rects.append(Rectangle((0, 0), 1, 1, fc=color))

    ax.grid(True)
    # Shrink current axis's height by 10% on the bottom
    box = ax.get_position()
    ax.set_position([box.x0, box.y0 + box.height * 0.1,
                     box.width, box.height * 0.9])

    ax.legend(rects, ['Unknown', 'VFR', 'MVFR', "IFR", "LIFR"],
              loc='upper center', fontsize=14,
              bbox_to_anchor=(0.5, -0.09), fancybox=True, shadow=True, ncol=5)

    return fig, df


if __name__ == '__main__':
    plotter(dict(station='DSM', year=2009, month=1, network='IA_ASOS'))
