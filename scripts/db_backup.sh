#!/bin/bash

pg_dump -Z0 -j 2 -Fd donationbot -f postgres-backup-donbot
tar -cf - postgres-backup-donbot | pigz -p 2 > postgres-backup-donbot.tar.gz
rm -rf postgres-backup-donbot

aws s3 cp postgres-backup-donbot.tar.gz s3://donationbot
rm postgres-backup-donbot.tar.gz

