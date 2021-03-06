"""The Daily Processor of Wx Data for Yield Forecast Project

 - Read the baseline from the database
 - Add columns GDD(F) ST4(C) ST12 ST24 ST50 SM12[frac] SM24 SM50
 - For each year, replace the Jan 1 to yesterday data with actual data
 - Replace today to day + 3 with forecast data
 - For this year, replace day + 4 to Dec 31 with CFS :)
 - Upload the resulting file <site>_YYYYmmdd.met
"""
from __future__ import print_function
import sys
import datetime
import tempfile
import os
import subprocess

import dropbox
import requests
import numpy as np
import pandas as pd
from pandas.io.sql import read_sql
from pyiem.datatypes import temperature, distance
from pyiem.meteorology import gdd
from pyiem.util import get_properties
import psycopg2

XREF = {'ames': {'isusm': 'BOOI4', 'climodat': 'IA0200'},
        'cobs': {'isusm': None, 'station': 'OT0012', 'climodat': 'IA0200'},
        'crawfordsville': {'isusm': 'CRFI4', 'climodat': 'IA8688'},
        'lewis': {'isusm': 'OKLI4', 'climodat': 'IA0364'},
        'nashua': {'isusm': 'NASI4', 'climodat': 'IA1402'},
        'sutherland': {'isusm': 'CAMI4', 'climodat': 'IA1442'}}

DO_UPLOAD = (len(sys.argv) == 1)
if not DO_UPLOAD:
    print("Disabling dropbox upload of results")


def p(val, prec):
    if val is None or np.isnan(val):
        return '99'
    _fmt = "%%.%sf" % (prec,)
    return _fmt % (val,)


def upload_summary_plots():
    """Some additional work"""
    props = get_properties()
    dbx = dropbox.Dropbox(props.get('dropbox.token'))
    year = datetime.date.today().year
    interval = 'jan1'
    for opt in ['yes', 'no']:
        for location in XREF:
            (tmpfd, tmpfn) = tempfile.mkstemp()
            uri = ("http://iem.local/plotting/auto/plot/143/"
                   "location:%s::s:%s::opt:%s::dpi:100.png"
                   ) % (location, interval, opt)
            res = requests.get(uri)
            os.write(tmpfd, res.content)
            os.close(tmpfd)
            today = datetime.date.today()
            remotefn = ("%s_%s_%s%s.png"
                        ) % (location, today.strftime("%Y%m%d"),
                             interval, '_yields' if opt == 'yes' else '')
            if DO_UPLOAD:
                try:
                    dbx.files_upload(
                        open(tmpfn).read(),
                        ("/YieldForecast/Daryl/%s vs other years plots%s/%s"
                         ) % (year, ' with yields' if opt == 'yes' else '',
                              remotefn),
                        mode=dropbox.files.WriteMode.overwrite)
                except Exception as _:
                    print('dropbox fail')
            os.unlink(tmpfn)


def write_and_upload(df, location):
    """ We are done, whew!"""
    props = get_properties()
    dbx = dropbox.Dropbox(props.get('dropbox.token'))
    (tmpfd, tmpfn) = tempfile.mkstemp()
    for line in open("baseline/%s.met" % (location, )):
        if line.startswith("year"):
            break
        os.write(tmpfd, line.strip()+"\r\n")
    os.write(tmpfd, ('! auto-generated at %sZ by daryl akrherz@iastate.edu\r\n'
                     ) % (datetime.datetime.utcnow().isoformat(),))
    fmt = ("%-10s%-10s%-10s%-10s%-10s%-10s"
           "%-10s%-10s%-10s%-10s%-10s%-10s%-10s%-10s\r\n")
    os.write(tmpfd, fmt % ('year', 'day', 'radn', 'maxt', 'mint', 'rain',
                           'gdd', 'st4', 'st12', 'st24', 'st50',
                           'sm12', 'sm24', 'sm50'))
    os.write(tmpfd, fmt % ('()', '()', '(MJ/m^2)', '(oC)', '(oC)', '(mm)',
                           '(oF)', '(oC)', '(oC)', '(oC)', '(oC)',
                           '(mm/mm)', '(mm/mm)', '(mm/mm)'))
    fmt = (" %-9i%-10i%-10s%-10s%-10s%-10s%-10s"
           "%-10s%-10s%-10s%-10s%-10s%-10s%-10s\r\n")
    for valid, row in df.iterrows():
        os.write(tmpfd, fmt % (valid.year,
                               int(valid.strftime("%j")),
                               p(row['radn'], 3),
                               p(row['maxt'], 1), p(row['mint'], 1),
                               p(row['rain'], 2),
                               p(row['gdd'], 1), p(row['st4'], 2),
                               p(row['st12'], 2),
                               p(row['st24'], 2), p(row['st50'], 2),
                               p(row['sm12'], 2),
                               p(row['sm24'], 2), p(row['sm50'], 2)))
    os.close(tmpfd)

    today = datetime.date.today()
    remotefn = "%s_%s.met" % (location, today.strftime("%Y%m%d"))
    if DO_UPLOAD:
        try:
            dbx.files_upload(
                open(tmpfn).read(),
                "/YieldForecast/Daryl/%s" % (remotefn, ),
                mode=dropbox.files.WriteMode.overwrite)
        except Exception as _:
            print('dropbox fail')
    # Save file for usage by web plotting...
    os.chmod(tmpfn, 0644)
    # os.rename fails here due to cross device link bug
    subprocess.call(("mv %s /mesonet/share/pickup/yieldfx/%s.met"
                     ) % (tmpfn, location), shell=True)


def qc(df):
    """Run some QC against the dataframe"""
    # Make sure our frame is sorted
    df.sort_index(inplace=True)


def load_baseline(location):
    """return a dataframe of this location's data"""
    pgconn = psycopg2.connect(database='coop', host='iemdb', user='nobody')
    df = read_sql("""
        SELECT *, extract(doy from valid) as doy,
        extract(year from valid) as year
        from yieldfx_baseline where station = %s ORDER by valid
        """, pgconn, params=(location,), index_col='valid')
    # we want data from 1980 to this year
    today = datetime.date.today()
    # So now, we need to move any data that exists for this year and overwrite
    # the previous years with that data.  This is QC'd prior to any new obs
    # are taken from ISUSM
    rcols = ['radn', 'maxt', 'mint', 'rain']
    for date, row in df[df['year'] == today.year].iterrows():
        for year in range(1980, today.year):
            if date.month == 2 and date.day == 29 and year % 4 != 0:
                continue
            df.loc[date.replace(year=year), rcols] = (row['radn'], row['maxt'],
                                                      row['mint'], row['rain'])
    # Fill out the time domain
    dec31 = today.replace(month=12, day=31)
    df = df.reindex(index=pd.date_range(datetime.date(1980, 1, 1), dec31).date)
    return df


def replace_forecast(df, location):
    """Replace dataframe data with forecast for this location"""
    pgconn = psycopg2.connect(database='coop', host='iemdb', user='nobody')
    cursor = pgconn.cursor()
    today = datetime.date.today()
    nextjan1 = datetime.date(today.year + 1, 1, 1)
    coop = XREF[location]['climodat']
    years = [int(y) for y in np.arange(df.index.values.min().year,
                                       df.index.values.max().year + 1)]
    cursor.execute("""
        SELECT day, high, low, precip from alldata_forecast WHERE
        modelid = (SELECT id from forecast_inventory WHERE model = 'NDFD'
        ORDER by modelts DESC LIMIT 1) and station = %s and day >= %s
    """, (coop, today))
    rcols = ['maxt', 'mint', 'rain']
    for row in cursor:
        valid = row[0]
        maxc = temperature(row[1], 'F').value('C')
        minc = temperature(row[2], 'F').value('C')
        rain = distance(row[3], 'IN').value('MM')
        for year in years:
            df.loc[valid.replace(year=year), rcols] = (maxc, minc, rain)

    # Need to get radiation from CFS
    cursor.execute("""
        SELECT day, srad from alldata_forecast WHERE
        modelid = (SELECT id from forecast_inventory WHERE model = 'CFS'
        ORDER by modelts DESC LIMIT 1) and station = %s and day >= %s
        and day < %s
    """, (coop, today, nextjan1))
    for row in cursor:
        valid = row[0]
        for year in years:
            df.loc[valid.replace(year=year), 'radn'] = row[1]


def replace_cfs(df, location):
    """Replace the CFS data for this year!"""
    pgconn = psycopg2.connect(database='coop', host='iemdb', user='nobody')
    cursor = pgconn.cursor()
    coop = XREF[location]['climodat']
    today = datetime.date.today() + datetime.timedelta(days=3)
    dec31 = today.replace(day=31, month=12)
    cursor.execute("""
        SELECT day, high, low, precip, srad from alldata_forecast WHERE
        modelid = (SELECT id from forecast_inventory WHERE model = 'CFS'
        ORDER by modelts DESC LIMIT 1) and station = %s and day >= %s
        and day <= %s ORDER by day ASC
    """, (coop, today, dec31))
    rcols = ['maxt', 'mint', 'rain', 'radn']
    for row in cursor:
        maxt = temperature(row[1], 'F').value('C')
        mint = temperature(row[2], 'F').value('C')
        rain = distance(row[3], 'IN').value('MM')
        radn = row[4]
        df.loc[row[0], rcols] = [maxt, mint, rain, radn]

    if row[0] == dec31:
        return
    now = row[0] + datetime.timedelta(days=1)
    # OK, if our last row does not equal dec31, we have some more work to do
    print(("  Replacing %s->%s with previous year's data"
           ) % (now, dec31))
    while now <= dec31:
        lastyear = now.replace(year=(now.year - 1))
        df.loc[now, rcols] = df.loc[lastyear, rcols]
        now += datetime.timedelta(days=1)


def replace_obs_iem(df, location):
    """Replace dataframe data with obs for this location

    Tricky part, if the baseline already provides data for this year, we should
    use it!
    """
    pgconn = psycopg2.connect(database='iem', host='iemdb', user='nobody')
    cursor = pgconn.cursor()
    station = XREF[location]['station']
    today = datetime.date.today()
    jan1 = today.replace(month=1, day=1)
    years = [int(y) for y in np.arange(df.index.values.min().year,
                                       df.index.values.max().year + 1)]

    table = "summary_%s" % (jan1.year,)
    cursor.execute("""
        select day, max_tmpf, min_tmpf, srad_mj, pday
        from """ + table + """ s JOIN stations t on (s.iemid = t.iemid)
        WHERE t.id = %s and max_tmpf is not null
        and day < 'TODAY' ORDER by day ASC
        """, (station,))
    rcols = ['maxt', 'mint', 'radn', 'gdd', 'rain']
    replaced = []
    for row in cursor:
        valid = row[0]
        # Does our df currently have data for this date?  If so, we shall do
        # no more
        dont_replace = not np.isnan(df.at[valid, 'mint'])
        if not dont_replace:
            replaced.append(valid)
        _gdd = gdd(temperature(row[1], 'F'), temperature(row[2], 'F'))
        for year in years:
            if valid.month == 2 and valid.day == 29 and year % 4 != 0:
                continue
            if dont_replace:
                df.loc[valid.replace(year=year),
                       rcols[3:-1]] = (_gdd,
                                       distance(row[4], 'in').value('mm'))
                continue
            df.loc[valid.replace(year=year), rcols] = (
                temperature(row[1], 'F').value('C'),
                temperature(row[2], 'F').value('C'), row[3],
                _gdd, distance(row[4], 'in').value('mm'))
    if len(replaced) > 0:
        print(("  used IEM Access %s from %s->%s"
               ) % (station, replaced[0], replaced[-1]))


def replace_obs(df, location):
    """Replace dataframe data with obs for this location

    Tricky part, if the baseline already provides data for this year, we should
    use it!
    """
    pgconn = psycopg2.connect(database='isuag', host='iemdb', user='nobody')
    cursor = pgconn.cursor()
    isusm = XREF[location]['isusm']
    today = datetime.date.today()
    jan1 = today.replace(month=1, day=1)
    years = [int(y) for y in np.arange(df.index.values.min().year,
                                       df.index.values.max().year + 1)]

    cursor.execute("""
        select valid, tair_c_max_qc, tair_c_min_qc, slrmj_tot_qc,
        vwc_12_avg_qc,
        vwc_24_avg_qc, vwc_50_avg_qc, tsoil_c_avg_qc, t12_c_avg_qc,
        t24_c_avg_qc, t50_c_avg_qc,
        rain_mm_tot_qc from sm_daily WHERE station = %s and valid >= %s
        ORDER by valid
        """, (isusm, jan1))
    rcols = ['maxt', 'mint', 'radn', 'gdd', 'sm12', 'sm24', 'sm50',
             'st4', 'st12', 'st24', 'st50', 'rain']
    replaced = []
    for row in cursor:
        valid = row[0]
        # Does our df currently have data for this date?  If so, we shall do
        # no more
        dont_replace = not np.isnan(df.at[valid, 'mint'])
        if not dont_replace:
            replaced.append(valid)
        _gdd = gdd(temperature(row[1], 'C'), temperature(row[2], 'C'))
        for year in years:
            if valid.month == 2 and valid.day == 29 and year % 4 != 0:
                continue
            if dont_replace:
                df.loc[valid.replace(year=year),
                       rcols[3:-1]] = (_gdd, row[4], row[5],
                                       row[6], row[7], row[8],
                                       row[9], row[10])
                continue
            df.loc[valid.replace(year=year), rcols] = (row[1], row[2], row[3],
                                                       _gdd, row[4], row[5],
                                                       row[6], row[7], row[8],
                                                       row[9], row[10], row[11]
                                                       )
    if len(replaced) > 0:
        print(("  replaced with obs from %s for %s->%s"
               ) % (isusm, replaced[0], replaced[-1]))


def compute_gdd(df):
    """Compute GDDs Please"""
    df['gdd'] = gdd(temperature(df['maxt'].values, 'C'),
                    temperature(df['mint'].values, 'C'))


def do(location):
    """Workflow for a particular location"""
    print("yieldfx_workflow: Processing '%s'" % (location,))
    # 1. Read baseline
    df = load_baseline(location)
    # 2. Add columns and observed data
    for colname in ['gdd', 'st4', 'st12', 'st24', 'st50', 'sm12', 'sm24',
                    'sm50']:
        df[colname] = None
    # 3. Do data replacement
    # TODO: what to do with RAIN!
    if location == 'cobs':
        replace_obs_iem(df, location)
    else:
        replace_obs(df, location)
    # 4. Add forecast data
    replace_forecast(df, location)
    # 5. Add CFS for this year
    replace_cfs(df, location)
    # 6. Compute GDD
    compute_gdd(df)
    # 7. QC
    qc(df)
    # 8. Write and upload the file
    write_and_upload(df, location)
    # 9. Upload summary plots
    upload_summary_plots()


def main(argv):
    """Do Something"""
    for location in XREF:
        do(location)


if __name__ == '__main__':
    main(sys.argv)
    # do('cobs')
