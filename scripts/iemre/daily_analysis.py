"""Grid the daily data onto a midwest grid for IEMRE

This is tricky as some variables we can compute sooner than others.  We run
this script twice per day:

    RUN_MIDNIGHT.sh for just the 'calendar day' variables yesterday
    RUN_NOON.sh for the 12z today vals and calendar day yesterday
"""
import os
import sys
import subprocess
import netCDF4
import numpy as np
from pandas.io.sql import read_sql
import datetime
import psycopg2
import pytz
from scipy.stats import zscore
from pyiem import iemre, datatypes
from psycopg2.extras import DictCursor
from scipy.interpolate import NearestNDInterpolator

pgconn = psycopg2.connect(database='iem', host='iemdb', user='nobody')
coop_pgconn = psycopg2.connect(database='coop', host='iemdb', user='nobody')
cursor = pgconn.cursor(cursor_factory=DictCursor)


def generic_gridder(df, idx):
    """
    Generic gridding algorithm for easy variables
    """
    # print(("Processing generic_gridder for column: %s min:%.2f max:%.2f"
    #       ) % (idx, df[idx].min(), df[idx].max()))
    if df[idx].max() == 0 and df[idx].max() == 0:
        return 0
    window = 2.0
    f1 = df[df[idx].notnull()]
    for lat in np.arange(iemre.SOUTH, iemre.NORTH, window):
        for lon in np.arange(iemre.WEST, iemre.EAST, window):
            (west, east, south, north) = (lon, lon + window, lat, lat + window)
            box = f1[(f1['lat'] >= south) & (f1['lat'] < north) &
                     (f1['lon'] >= west) & (f1['lon'] < east)]
            # can't QC data that is all equal
            if len(box.index) < 4 or box[idx].min() == box[idx].max():
                continue
            z = np.abs(zscore(box[idx]))
            # Compute where the standard dev is +/- 2std
            bad = box[z > 1.5]
            df.loc[bad.index, idx] = np.nan
            # for _, row in bad.iterrows():
            #    print _, idx, row['station'], row['name'], row[idx]

    good = df[df[idx].notnull()]
    if len(good.index) < 4:
        print("Not enough data %s" % (idx,))
        return
    nn = NearestNDInterpolator((np.array(good['lon']),
                                np.array(good['lat'])),
                               np.array(good[idx]))
    xi, yi = np.meshgrid(iemre.XAXIS, iemre.YAXIS)
    grid = nn(xi, yi)

    return grid


def do_precip(nc, ts):
    """Compute the 6 UTC to 6 UTC precip

    We need to be careful here as the timestamp sent to this app is today,
    we are actually creating the analysis for yesterday
    """
    sts = datetime.datetime(ts.year, ts.month, ts.day, 6)
    sts = sts.replace(tzinfo=pytz.timezone("UTC"))
    ets = sts + datetime.timedelta(hours=24)
    offset = iemre.daily_offset(ts)
    offset1 = iemre.hourly_offset(sts)
    offset2 = iemre.hourly_offset(ets)
    if ts.month == 12 and ts.day == 31:
        print(("p01d      for %s [idx:%s] %s(%s)->%s(%s) SPECIAL"
               ) % (ts, offset, sts.strftime("%Y%m%d%H"), offset1,
                    ets.strftime("%Y%m%d%H"), offset2))
        ncfn = "/mesonet/data/iemre/%s_mw_hourly.nc" % (ets.year,)
        if not os.path.isfile(ncfn):
            print("Missing %s" % (ncfn,))
            return
        hnc = netCDF4.Dataset(ncfn)
        phour = np.sum(hnc.variables['p01m'][:offset2, :, :], 0)
        hnc.close()
        hnc = netCDF4.Dataset("/mesonet/data/iemre/%s_mw_hourly.nc" % (
            sts.year,))
        phour += np.sum(hnc.variables['p01m'][offset1:, :, :], 0)
        hnc.close()
    else:
        if sts.year >= 1900:
            print(("p01d      for %s [idx:%s] %s(%s)->%s(%s)"
                   ) % (ts, offset, sts.strftime("%Y%m%d%H"), offset1,
                        ets.strftime("%Y%m%d%H"), offset2))
        ncfn = "/mesonet/data/iemre/%s_mw_hourly.nc" % (sts.year,)
        if not os.path.isfile(ncfn):
            print("Missing %s" % (ncfn,))
            return
        hnc = netCDF4.Dataset(ncfn)
        phour = np.sum(hnc.variables['p01m'][offset1:offset2, :, :], 0)
        hnc.close()
    nc.variables['p01d'][offset] = phour


def do_precip12(nc, ts):
    """Compute the 24 Hour precip at 12 UTC, we do some more tricks though"""
    offset = iemre.daily_offset(ts)
    ets = datetime.datetime(ts.year, ts.month, ts.day, 12)
    ets = ets.replace(tzinfo=pytz.timezone("UTC"))
    sts = ets - datetime.timedelta(hours=24)
    offset1 = iemre.hourly_offset(sts)
    offset2 = iemre.hourly_offset(ets)
    if ts.month == 1 and ts.day == 1:
        if sts.year >= 1900:
            print(("p01d_12z  for %s [idx:%s] %s(%s)->%s(%s) SPECIAL"
                   ) % (ts, offset, sts.strftime("%Y%m%d%H"), offset1,
                        ets.strftime("%Y%m%d%H"), offset2))
        ncfn = "/mesonet/data/iemre/%s_mw_hourly.nc" % (ets.year,)
        if not os.path.isfile(ncfn):
            print("Missing %s" % (ncfn,))
            return
        hnc = netCDF4.Dataset(ncfn)
        phour = np.sum(hnc.variables['p01m'][:offset2, :, :], 0)
        hnc.close()
        hnc = netCDF4.Dataset("/mesonet/data/iemre/%s_mw_hourly.nc" % (
            sts.year,))
        phour += np.sum(hnc.variables['p01m'][offset1:, :, :], 0)
        hnc.close()
    else:
        if sts.year >= 1900:
            print(("p01d_12z  for %s [idx:%s] %s(%s)->%s(%s)"
                   ) % (ts, offset, sts.strftime("%Y%m%d%H"), offset1,
                        ets.strftime("%Y%m%d%H"), offset2))
        ncfn = "/mesonet/data/iemre/%s_mw_hourly.nc" % (ts.year,)
        if not os.path.isfile(ncfn):
            print("Missing %s" % (ncfn,))
            return
        hnc = netCDF4.Dataset(ncfn)
        phour = np.sum(hnc.variables['p01m'][offset1:offset2, :, :], 0)
        hnc.close()
    nc.variables['p01d_12z'][offset] = phour


def plot(df):
    from pyiem.plot import MapPlot
    m = MapPlot(sector='midwest', continentalcolor='white')
    m.plot_values(df['lon'].values, df['lat'].values, df['highdata'].values,
                  labelbuffer=0)
    m.postprocess(filename='test.png')
    m.close()


def grid_day12(nc, ts):
    """Use the COOP data for gridding
    """
    offset = iemre.daily_offset(ts)
    print(('12z hi/lo for %s [idx:%s]') % (ts, offset))
    if ts.year > 2008:
        sql = """
           SELECT ST_x(s.geom) as lon, ST_y(s.geom) as lat, s.state,
           s.id as station, s.name as name,
           (CASE WHEN pday >= 0 then pday else null end) as precipdata,
           (CASE WHEN snow >= 0 then snow else null end) as snowdata,
           (CASE WHEN snowd >= 0 then snowd else null end) as snowddata,
           (CASE WHEN max_tmpf > -50 and max_tmpf < 130
               then max_tmpf else null end) as highdata,
           (CASE WHEN min_tmpf > -50 and min_tmpf < 95
               then min_tmpf else null end) as lowdata
           from summary_%s c, stations s WHERE day = '%s' and
           s.network in ('IA_COOP', 'MN_COOP', 'WI_COOP', 'IL_COOP', 'MO_COOP',
            'KS_COOP', 'NE_COOP', 'SD_COOP', 'ND_COOP', 'KY_COOP', 'MI_COOP',
            'OH_COOP', 'IN_COOP') and c.iemid = s.iemid and
            extract(hour from c.coop_valid) between 4 and 11
            """ % (ts.year, ts.strftime("%Y-%m-%d"))
        df = read_sql(sql, pgconn)
    else:
        df = read_sql("""
        WITH mystations as (
            SELECT id, ST_X(geom) as lon, ST_Y(geom) as lat, state, name
            from stations where network in ('IACLIMATE', 'MNCLIMATE',
            'WICLIMATE', 'ILCLIMATE', 'MOCLIMATE', 'KSCLIMATE', 'NECLIMATE',
            'SDCLIMATE', 'NDCLIMATE', 'KYCLIMATE', 'MICLIMATE', 'OHCLIMATE',
            'INCLIMATE') and (temp24_hour is null or
            temp24_hour between 4 and 10)
        )
        SELECT m.lon, m.lat, m.state, m.id as station, m.name as name,
        precip as precipdata, snow as snowdata, snowd as snowddata,
        high as highdata, low as lowdata from alldata a JOIN mystations m
        ON (a.station = m.id) WHERE a.day = %s
        """, coop_pgconn, params=(ts,))
    # plot(df)

    if len(df.index) > 4:
        res = generic_gridder(df, 'highdata')
        nc.variables['high_tmpk_12z'][offset] = datatypes.temperature(
                                                res, 'F').value('K')
        print(("12z hi for %s [idx:%s] "
               "min: %5.1f max: %5.1f"
               ) % (ts, offset, np.min(res), np.max(res)))

        res = generic_gridder(df, 'lowdata')
        nc.variables['low_tmpk_12z'][offset] = datatypes.temperature(
                                            res, 'F').value('K')
        print(("12z lo for %s [idx:%s] "
               "min: %5.1f max: %5.1f"
               ) % (ts, offset, np.min(res), np.max(res)))

        res = generic_gridder(df, 'snowdata')
        nc.variables['snow_12z'][offset] = res * 25.4

        res = generic_gridder(df, 'snowddata')
        nc.variables['snowd_12z'][offset] = res * 25.4
    else:
        print "%s has %02i entries, FAIL" % (ts.strftime("%Y-%m-%d"),
                                             len(df.index))


def grid_day(nc, ts):
    """
    """
    offset = iemre.daily_offset(ts)
    if ts.year > 1927:
        sql = """
           SELECT ST_x(s.geom) as lon, ST_y(s.geom) as lat, s.state,
           s.name, s.id as station,
           (CASE WHEN pday >= 0 then pday else null end) as precipdata,
           (CASE WHEN max_tmpf > -50 and max_tmpf < 130
               then max_tmpf else null end) as highdata,
           (CASE WHEN min_tmpf > -50 and min_tmpf < 95
               then min_tmpf else null end) as lowdata,
           (CASE WHEN max_dwpf > -50 and max_dwpf < 130
               then max_dwpf else null end) as highdwpf,
           (CASE WHEN min_dwpf > -50 and min_dwpf < 95
               then min_dwpf else null end) as lowdwpf,
            (CASE WHEN avg_sknt >= 0 and avg_sknt < 100
             then avg_sknt else null end) as avgsknt
           from summary_%s c, stations s WHERE day = '%s' and
           s.network in ('IA_ASOS', 'MN_ASOS', 'WI_ASOS', 'IL_ASOS', 'MO_ASOS',
            'KS_ASOS', 'NE_ASOS', 'SD_ASOS', 'ND_ASOS', 'KY_ASOS', 'MI_ASOS',
            'OH_ASOS', 'AWOS', 'IN_ASOS') and c.iemid = s.iemid
            """ % (ts.year, ts.strftime("%Y-%m-%d"))
        df = read_sql(sql, pgconn)
    else:
        df = read_sql("""
        WITH mystations as (
            SELECT id, ST_X(geom) as lon, ST_Y(geom) as lat, state, name
            from stations where network in ('IACLIMATE', 'MNCLIMATE',
            'WICLIMATE', 'ILCLIMATE', 'MOCLIMATE', 'KSCLIMATE', 'NECLIMATE',
            'SDCLIMATE', 'NDCLIMATE', 'KYCLIMATE', 'MICLIMATE', 'OHCLIMATE',
            'INCLIMATE') and (temp24_hour is null or
            temp24_hour between 4 and 10)
        )
        SELECT m.lon, m.lat, m.state, m.id as station, m.name as name,
        precip as precipdata, snow as snowdata, snowd as snowddata,
        high as highdata, low as lowdata,
        null as highdwpf, null as lowdwpf, null as avgsknt
        from alldata a JOIN mystations m
        ON (a.station = m.id) WHERE a.day = %s
        """, coop_pgconn, params=(ts,))
    if len(df.index) > 4:
        res = generic_gridder(df, 'highdata')
        nc.variables['high_tmpk'][offset] = datatypes.temperature(
                                                res, 'F').value('K')
        print(("cal hi for %s [idx:%s] "
               "min: %5.1f max: %5.1f"
               ) % (ts, offset, np.min(res), np.max(res)))
        res = generic_gridder(df, 'lowdata')
        nc.variables['low_tmpk'][offset] = datatypes.temperature(
                                            res, 'F').value('K')
        print(("cal lo for %s [idx:%s] "
               "min: %5.1f max: %5.1f"
               ) % (ts, offset, np.min(res), np.max(res)))
        hres = generic_gridder(df, 'highdwpf')
        lres = generic_gridder(df, 'lowdwpf')
        if hres is not None and lres is not None:
            nc.variables['avg_dwpk'][offset] = datatypes.temperature(
                                            (hres + lres) / 2., 'F').value('K')
        res = generic_gridder(df, 'avgsknt')
        if res is not None:
            res = np.where(res < 0, 0, res)
            nc.variables['wind_speed'][offset] = datatypes.speed(
                                                res, 'KT').value('MPS')
    else:
        print "%s has %02i entries, FAIL" % (ts.strftime("%Y-%m-%d"),
                                             cursor.rowcount)


def main(ts, irealtime):
    # Load up our netcdf file!
    ncfn = "/mesonet/data/iemre/%s_mw_daily.nc" % (ts.year,)
    if not os.path.isfile(ncfn):
        print("will create %s" % (ncfn, ))
        cmd = "python init_daily.py %s" % (ts.year,)
        subprocess.call(cmd, shell=True)
    nc = netCDF4.Dataset(ncfn, 'a')
    # For this date, the 12 UTC COOP obs will match the date
    grid_day12(nc, ts)
    do_precip12(nc, ts)
    nc.close()
    # This is actually yesterday!
    if irealtime:
        ts -= datetime.timedelta(days=1)
    ncfn = "/mesonet/data/iemre/%s_mw_daily.nc" % (ts.year,)
    if not os.path.isfile(ncfn):
        print("will create %s" % (ncfn, ))
        cmd = "python init_daily.py %s" % (ts.year,)
        subprocess.call(cmd, shell=True)
    nc = netCDF4.Dataset(ncfn, 'a')
    grid_day(nc, ts)
    do_precip(nc, ts)
    nc.close()

if __name__ == "__main__":
    if len(sys.argv) == 4:
        ts = datetime.date(int(sys.argv[1]), int(sys.argv[2]),
                           int(sys.argv[3]))
        main(ts, False)
    else:
        ts = datetime.date.today()
        main(ts, True)
