FROM python:3.12.3

WORKDIR /home/app

#If we add the requirements and install dependencies first, docker can use cache if requirements don't change
ADD requirements.txt /home/app
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 3000
        