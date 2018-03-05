FROM golang:1.9 as builder
WORKDIR /root/threes-ai
COPY . .
RUN go get github.com/halfrost/threes-ai/utils
RUN go get github.com/halfrost/threes-ai/gameboard
RUN go get github.com/gorilla/websocket
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o threes-ai .

FROM alpine:latest
LABEL maintainer="ydz@627@gmail.com"
RUN apk --no-cache add ca-certificates tzdata \
			&& cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
			&& echo "Asia/Shanghai" >  /etc/timezone \
			&& apk del tzdata
WORKDIR .
COPY --from=builder /root/threes-ai/threes-ai .
EXPOSE 9000
CMD ["./threes-ai"]
