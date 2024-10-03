import subprocess
import datetime
import json
import os
from threading import Lock
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

LOGS_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_FILE = os.path.join(LOGS_DIR, 'logs.txt')
lock = Lock()

# Keep track of the number of requests
request_counter = 0

def get_cpu_usage():
    logger.info("Getting CPU usage")
    command = "ps -eo pcpu | awk 'NR>1 {sum += $1} END {print sum}'"
    result = subprocess.run(command, capture_output=True, shell=True, text=True)
    if result.returncode == 0:
        cpu_usage = result.stdout.strip() + '%'
        logger.info(f"CPU usage: {cpu_usage}")
        return cpu_usage
    else:
        logger.error("Error obtaining CPU usage")
        return "Error obtaining CPU usage"

def trim_logs():
    logger.info("Trimming logs to keep the size manageable")
    with lock:
        try:
            with open(LOGS_FILE, 'r+') as file:
                lines = file.readlines()
                if len(lines) > 500:
                    logger.info("Log file size exceeds 500 lines, trimming")
                    file.seek(0)
                    file.truncate()
                    file.writelines(lines[-500:])
        except FileNotFoundError:
            logger.warning(f"Log file {LOGS_FILE} not found for trimming")

def log_request_stats(request_type, endpoint):
    global request_counter
    try:
        timestamp = datetime.datetime.now().isoformat()
        cpu_usage = get_cpu_usage()

        with lock:
            request_counter += 1
            current_request_count = request_counter

            log_entry = {
                'timestamp': timestamp,
                'request_type': request_type,
                'endpoint': endpoint,
                'CPU_usage': cpu_usage,
                'simultaneous_requests': current_request_count
            }

            logger.info(f"Logging request: {log_entry}")
            with open(LOGS_FILE, 'a') as log_file:
                log_file.write(json.dumps(log_entry) + '\n')

        trim_logs()

    except Exception as e:
        logger.error(f"An error occurred while logging request stats: {e}", exc_info=True)
    finally:
        with lock:
            request_counter -= 1

#git change