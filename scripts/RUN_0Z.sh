# Ensure this is actually being run at 00z, since crontab is in CST/CDT
HH=$(date -u +%H)
if [ "$HH" -ne "00" ]
	then
		exit
fi

cd util
python make_archive_baseline.py

# Wait a bit, so that more obs can come in
sleep 300

cd ../00z
python awos_rtp.py

cd ../ingestors
python elnino.py

# nexrad N0R and N0Q composites
cd ../summary
python max_reflect.py

# Rerun today
cd ../dbutil
python rwis2archive.py $(date -u --date '1 days ago' +'%Y %m %d')
python ot2archive.py $(date -u --date '1 days ago' +'%Y %m %d')
python snet2archive.py

cd ../iemre
python stage4_12z_adjust.py

cd ../dl
# at 0z, -6 days is available, hopefully!
#python download_narr.py $(date -u --date '6 days ago' +'%Y %m %d')
#python download_narr.py $(date -u --date '30 days ago' +'%Y %m %d')
#python download_nldas.py

cd ../qc
python check_n0q.py
