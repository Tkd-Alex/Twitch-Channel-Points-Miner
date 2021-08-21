# Run Twitch Channel Points Miner v2 in a Docker container

Docker offers an easy way to run an app in an isolated space, bundled with its 
requirements and separated from the host system and other containers.

The Dockerfile uses a small python image, installs all requirements, the app
and cares for running `run.py` when the container is started.

`run.py` resides on the host system and needs to be mapped into the container 
during startup since it contains the configuration.

It is recommended to also map the folders *cookies* and *analytics* to a volume 
or folder on the host system to make sure that cookies (important to stay logged in 
if 2FA is enabled in Twitch) and analytics is preserved even in case of container 
re-creation or updates.


## Building the Docker image

With Docker installed, run:

```bash
docker build -t tcpm .
```

After the build, the container image can easily be tested by running:

```bash
docker run -it --rm tcpm
```

This should print a message which tells that there is no actual `run.py` 
mapped into the container - which is perfectly fine.


## Running the docker image

```bash
docker run -d -p 5000:5000 \
-v /path/to/your/run.py:/Twitch-Channel-Points-Miner-v2/run.py \
-v /path/to/your/cookies/folder:/Twitch-Channel-Points-Miner-v2/cookies \
-v /path/to/your/analytics/folder:/Twitch-Channel-Points-Miner-v2/analytics \
--name miner --restart unless-stopped tcpm
```

Probably your Twitch account needs a verfication code on the first login from a new machine. 
In This case start the container attached for the first run:

```bash
docker run -it -p 5000:5000 \
-v /path/to/your/run.py:/Twitch-Channel-Points-Miner-v2/run.py \
-v /path/to/your/cookies/folder:/Twitch-Channel-Points-Miner-v2/cookies \
-v /path/to/your/analytics/folder:/Twitch-Channel-Points-Miner-v2/analytics \
--name miner tcpm
```

After that, you can start the container in detached mode:

```bash
docker start --restart unless-stopped miner
```
