"""Script for logging to InfluxDB."""
import time
import sys
import json
import logging
import asyncio
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from urllib3.exceptions import ReadTimeoutError
import onewire

# cfg_file = files('scripts'), 'influxdb_config.json')

async def get_data(device_host: str):
    """Get data from Onewire asynchronously"""
    async with onewire.ONEWIRE(device_host) as ow:
        await ow.get_data()
    return ow.ow_data

def main(config_file):
    """Query user for setup info and start logging to InfluxDB."""

    # read the config file
    with open(config_file, encoding='utf-8') as cfg_file:
        cfg = json.load(cfg_file)

    verbose = cfg['verbose'] == 1

    # Do we have a logfile?
    if cfg['logfile'] is not None:
        # log to a file
        logger = logging.getLogger(cfg['logfile'])
        if verbose:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler = logging.FileHandler(cfg['logfile'])
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    else:
        logger = None

    # get channels to log
    channels = cfg['log_channels']

    # Try/except to catch exceptions
    db_client = None
    try:
        # Loop until ctrl-C
        while True:
            try:
                # Connect to onewire
                if verbose:
                    print("Connecting to OneWire controller...")
                if logger:
                    logger.info('Connecting to OneWire controller...')
                ow = asyncio.run(get_data(cfg['device_host']))
                ow_data = ow.read_sensors()[0]

                # Connect to InfluxDB
                if verbose:
                    print("Connecting to InfluxDB...")
                if logger:
                    logger.info('Connecting to InfluxDB...')
                db_client = InfluxDBClient(url=cfg['db_url'], token=cfg['db_token'],
                                           org=cfg['db_org'])
                write_api = db_client.write_api(write_options=SYNCHRONOUS)

                for chan in channels:
                    value = ow_data[chan]
                    point = (
                        Point("onewire")
                        .field(channels[chan]['field'], value)
                        .tag("units", channels[chan]['units'])
                        .tag("channel", f"{cfg['db_channel']}")
                    )
                    write_api.write(bucket=cfg['db_bucket'], org=cfg['db_org'], record=point)
                    if verbose:
                        print(point)
                    if logger:
                        logger.debug(point)

                # Close db connection
                if verbose:
                    print("Closing connection to InfluxDB...")
                if logger:
                    logger.info('Closing connection to InfluxDB...')
                db_client.close()
                db_client = None

            # Handle exceptions
            except ReadTimeoutError as e:
                print(f"ReadTimeoutError: {e}, will retry.")
                if logger:
                    logger.critical("ReadTimeoutError: %s, will retry.", e)
            except Exception as e:
                print(f"Unexpected error: {e}, will retry.")
                if logger:
                    logger.critical("Unexpected error: %s, will retry.", e)

            # Sleep for interval_secs
            if verbose:
                print(f"Waiting {cfg['interval_secs']:d} seconds...")
            if logger:
                logger.info("Waiting %d seconds...", cfg['interval_secs'])
            time.sleep(cfg['interval_secs'])

    except KeyboardInterrupt:
        print("\nShutting down InfluxDB logging...")
        if logger:
            logger.critical("Shutting down InfluxDB logging...")
        if db_client:
            db_client.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python influxdb_log.py <influxdb_log.json>")
        sys.exit(0)
    main(sys.argv[1])
