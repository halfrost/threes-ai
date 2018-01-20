package main

import (
	"flag"
	"fmt"
	"html/template"
	"log"
	"net/http"

	"github.com/gorilla/websocket"
)

var logo = `
______   __  __     ______     ______     ______     ______     ______     __
/\__  _\ /\ \_\ \   /\  == \   /\  ___\   /\  ___\   /\  ___\   /\  __ \   /\ \
\/_/\ \/ \ \  __ \  \ \  __<   \ \  __\   \ \  __\   \ \___  \  \ \  __ \  \ \ \
  \ \_\  \ \_\ \_\  \ \_\ \_\  \ \_____\  \ \_____\  \/\_____\  \ \_\ \_\  \ \_\
   \/_/   \/_/\/_/   \/_/ /_/   \/_____/   \/_____/   \/_____/   \/_/\/_/   \/_/

`
var upgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	CheckOrigin: func(r *http.Request) bool {
		return true
	},
}

var (
	addr   = flag.String("addr", ":8900", "http service address")
	online int32
)

func main() {
	fmt.Println(logo)
	flag.Parse()
	static := http.FileServer(http.Dir("./threes!"))
	http.Handle("/bundle/", static)

	indexTpl := template.Must(template.ParseFiles("./threes!/bundle/programs/client/app.html"))
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		indexTpl.Execute(w, nil)
	})
	http.HandleFunc("/compute", compute)

	log.Printf("Service started on \x1b[32;1m%s\x1b[32;1m\x1b[0m\n", *addr)
	log.Fatal(http.ListenAndServe(*addr, nil))
}

func compute(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Println("upgrade error:", err.Error())
		return
	}
	defer func() {
		if conn != nil {
			conn.Close()
		}
		// online = atomic.AddInt32(&online, -1)
		// log.Println(online)
	}()
	// online = atomic.AddInt32(&online, 1)
	// log.Println(online)
	for {
		messageType, p, err := conn.ReadMessage()
		if err != nil {
			break
		}
		fmt.Printf("messageType = %v | p = %v\n", messageType, p)
		// g := &grid.Grid{}
		// if err = json.Unmarshal(p, g); err != nil {
		// 	break
		// }
		// a := &ai.AI{Grid: g}
		// dire := a.Search()
		// result := map[string]grid.Direction{"dire": dire}
		// p, _ = json.Marshal(result)
		// if err := conn.WriteMessage(messageType, p); err != nil {
		// 	break
		// }
	}
}
