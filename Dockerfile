FROM python:3.9-slim-buster
COPY . /Twitch-Channel-Points-Miner-v2
WORKDIR /Twitch-Channel-Points-Miner-v2
RUN apt-get update \
 && apt-get install gcc libffi-dev rustc zlib1g-dev libjpeg-dev libssl-dev --assume-yes \
 && pip install -r requirements.txt \
 && pip cache purge \
 && apt-get remove gcc rustc --assume-yes \
 && apt-get autoremove --assume-yes \
 && rm -rf /var/lib/apt/lists/* \
 && echo 'print("The container works, but there is no startup config provided.\
 \\nMake sure to map your run.py to /Twitch-Channel-Points-Miner-v2/run.py\
 when starting the container.");' > run.py
CMD python run.py
