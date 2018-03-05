package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/gorilla/websocket"
	"github.com/halfrost/threes-ai/ai"
	"github.com/halfrost/threes-ai/gameboard"
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

// RevData define
type RevData struct {
	Data [][]int
	Next int
}

func main() {
	fmt.Println(logo)
	utils.InitGameScoreTable()
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
		d := &RevData{}
		if err = json.Unmarshal(p, d); err != nil {
			break
		}
		fmt.Printf("接收到的数据是 = %v\n", d)
		nextBrick := make([]int, 0)
		nextBrick = append(nextBrick, d.Next)
		cand := gameboard.FindCandidates(d.Data)

		utils.PrintfGame(d.Data, cand, nextBrick)
		move := ai.ExpectSearch(d.Data, cand, nextBrick)

		result := make(map[string]int, 0)
		result["dire"] = move
		p, _ = json.Marshal(result)

		// control speed
		time.Sleep(160 * time.Millisecond)

		if err := conn.WriteMessage(messageType, p); err != nil {
			break
		}
	}
}

//export search_move
func search_move(board uint64, deck uint32, tileset uint16) int {
	//cand, _ := utils.GetCandidates(deck)
	b := utils.GetBoard(board)
	move := ai.ExpectSearch(b, gameboard.FindCandidates(b), utils.GetNextBrick(tileset))
	fmt.Printf("执行的移动是 = %v\n\n\n\n\n", move)
	return move
}

//export init_game
func init_game() {
	utils.InitGameScoreTable()
	fmt.Printf("【初始化】\n")
}

//export print_game
func print_game(board uint64, deck uint32, tileset uint16) {
	cand, _ := utils.GetCandidates(deck)
	utils.PrintfGame(utils.GetBoard(board), cand, utils.GetNextBrick(tileset))
}
