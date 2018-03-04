FROM node:8.9.4
WORKDIR /root/threes-ai/bundle
COPY ./threes!/dist/bundle .
EXPOSE 9888
CMD ROOT_URL=http://127.0.0.1 PORT=9888 node main.js
