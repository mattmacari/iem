"""Besting previous record"""
from pyiem.util import get_autoplot_context
from pyiem.network import Table as NetworkTable
import psycopg2
import pandas as pd


def get_description():
    """ Return a dict describing how to call this plotter """
    desc = dict()
    desc['highcharts'] = True
    desc['data'] = True
    desc['description'] = """This chart shows the margin by which new daily high
    and low temperatures set are beaten by.
    """
    desc['arguments'] = [
        dict(type='station', name='station', default='IA2203',
             label='Select Station:', network='IACLIMATE'),
        ]
    return desc


def get_context(fdict):
    """ Make the pandas Data Frame please"""
    pgconn = psycopg2.connect(dbname='coop', host='iemdb', user='nobody')
    cursor = pgconn.cursor()
    ctx = get_autoplot_context(fdict, get_description())
    station = ctx['station']
    network = ctx['network']
    nt = NetworkTable(network)
    table = "alldata_%s" % (station[:2],)
    cursor.execute("""
        SELECT day, sday, high, low from """ + table + """ WHERE station = %s
        and high is not null and low is not null
        ORDER by day ASC
    """, (station, ))
    dates = pd.date_range('2000/01/01', '2000/12/31').strftime("%m%d")
    records = pd.DataFrame(dict(high=-9999, low=9999),
                           index=dates)
    rows = []
    for row in cursor:
        if row[2] > records.at[row[1], 'high']:
            margin = row[2] - records.at[row[1], 'high']
            records.at[row[1], 'high'] = row[2]
            if margin < 1000:
                rows.append(dict(margin=margin, date=row[0]))
        if row[3] < records.at[row[1], 'low']:
            margin = row[3] - records.at[row[1], 'low']
            records.at[row[1], 'low'] = row[3]
            if margin > -1000:
                rows.append(dict(margin=margin, date=row[0]))

    ctx['df'] = pd.DataFrame(rows)
    ctx['title'] = "[%s] %s Daily Record Margin" % (station,
                                                    nt.sts[station]['name'])
    ctx['subtitle'] = "By how much did a new daily record beat the previous"
    return ctx


def highcharts(fdict):
    """ Do highcharts option"""
    ctx = get_context(fdict)
    ctx['df']['date'] = pd.to_datetime(ctx['df']['date'])
    df2 = ctx['df'][ctx['df']['margin'] > 0]
    v = df2[['date', 'margin']].to_json(orient='values')
    df2 = ctx['df'][ctx['df']['margin'] < 0]
    v2 = df2[['date', 'margin']].to_json(orient='values')
    series = """{
        data: """ + v + """,
        color: '#ff0000',
        name: 'High Temp Beat'
    },{
        data: """ + v2 + """,
        color: '#0000ff',
        name: 'Low Temp Beat'
    }
    """
    return """
    $("#ap_container").highcharts({
        global: {useUTC: true}, // needed since we are using dates here :/
        chart: {
            type: 'scatter',
            zoomType: 'x'
        },
        tooltip: {
            valueDecimals: 0,
            pointFormat: 'Date: <b>{point.x:%b %d, %Y}</b>' +
                          '<br/>Margin: <b>{point.y}</b><br/>'},
        yAxis: {title: {text: 'Temperature Beat Margin F'}},
        xAxis: {type: 'datetime'},
        title: {text: '""" + ctx['title'] + """'},
        subtitle: {text: '""" + ctx['subtitle'] + """'},
        series: [""" + series + """]
    });

    """


def plotter(fdict):
    """ Go """
    import matplotlib
    matplotlib.use('agg')
    import matplotlib.pyplot as plt
    ctx = get_context(fdict)

    (fig, ax) = plt.subplots(1, 1, figsize=(8, 6))
    df2 = ctx['df'][ctx['df']['margin'] > 0]
    ax.scatter(df2['date'].values, df2['margin'].values, color='r')

    df2 = ctx['df'][ctx['df']['margin'] < 0]
    ax.scatter(df2['date'].values, df2['margin'].values, color='b')
    ax.set_ylim(-30, 30)
    ax.grid(True)
    ax.set_ylabel("Temperature Beat Margin $^\circ$F")
    ax.set_title("%s\n%s" % (ctx['title'], ctx['subtitle']))

    return fig, ctx['df']


if __name__ == '__main__':
    highcharts(dict())
