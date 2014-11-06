# Redirector for tmpnb

A simple service that redirects to hosts running tmpnb,
with load-balancing based on their current availability.

Run the service:

    python redirector.py

Add hosts to be considered for redirection:

    curl -X POST -d '{"host": "https://tmpnb.org"}' http://127.0.0.1:9001/hosts

You can remove instances with a DELETE request:

    curl -X DELETE -d '{"host": "https://tmpnb.org"}' http://127.0.0.1:9001/hosts
