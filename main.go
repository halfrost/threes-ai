package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"

	"github.com/gorilla/websocket"
	"github.com/halfrost/threes-ai/ai"
	"github.com/halfrost/threes-ai/utils"
)

import "C"

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
	addr   = flag.String("addr", ":9000", "http service address")
	online int32
)

func main() {
	fmt.Println(logo)
	flag.Parse()
	log.SetFlags(0)
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
			log.Println("read error:", err)
			break
		}
		log.Printf("recv message: %s\n", string(p))
		// g := &grid.Grid{}
		// if err = json.Unmarshal(p, g); err != nil {
		// 	break
		// }
		// a := &ai.AI{Grid: g}
		// dire := a.Search()
		// result := map[string]grid.Direction{"dire": dire}
		// p, _ = json.Marshal(result)
		result := make(map[string]string, 0)
		result["data"] = "这是服务器返回信息"
		p, _ = json.Marshal(result)
		if err := conn.WriteMessage(messageType, p); err != nil {
			break
		}
	}
}

//export search_move
func search_move(board uint64, deck uint32, tileset uint16) float64 {
	cand, _ := utils.GetCandidates(deck)
	ai.ExpectSearch(utils.GetBoard(board), cand, utils.GetNextBrick(tileset))
	return 0
}

//export init_game
func init_game() {
	ai.InitGameState()
	fmt.Printf("【初始化】\n")
}

//export print_game
func print_game(board uint64, deck uint32, tileset uint16) {
	cand, _ := utils.GetCandidates(deck)
	utils.PrintfGame(utils.GetBoard(board), cand, utils.GetNextBrick(tileset))
}
