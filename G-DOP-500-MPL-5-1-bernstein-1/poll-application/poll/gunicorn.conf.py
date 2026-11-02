import os

bind = "0.0.0.0:80"
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
threads = 4
graceful_timeout = 20
accesslog = "-"
control_socket_disable = True
