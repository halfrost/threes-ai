// Command serve is a tiny static file server for the project (replay viewer,
// results JSON, and later the WASM demo). Go-based so it does not depend on a
// working system Python.
//
// Usage: go run ./cmd/serve -addr :8000 -dir .
package main

import (
	"flag"
	"log"
	"net/http"
)

func main() {
	addr := flag.String("addr", ":8000", "listen address")
	dir := flag.String("dir", ".", "directory to serve")
	flag.Parse()
	log.Printf("serving %s on http://localhost%s", *dir, *addr)
	log.Fatal(http.ListenAndServe(*addr, http.FileServer(http.Dir(*dir))))
}
