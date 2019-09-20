#!/bin/bash
/home/admin/Desktop/sample_work/GenericsAPI/test_local/run_docker.sh run --rm -v /home/admin/Desktop/sample_work/GenericsAPI/test_local/subjobs/$1/workdir:/kb/module/work -v /home/admin/Desktop/sample_work/GenericsAPI/test_local/workdir/tmp:/kb/module/work/tmp $4 -e "SDK_CALLBACK_URL=$3" $2 async
