package main

import (
	"io"
	"net/http"
	"os"
	"strconv"
	"sync/atomic"
	"time"

	"github.com/hongzhidao/worker/go"
)

var arrivals int32
var ready = make(chan struct{})

func handler(w http.ResponseWriter, r *http.Request) {
	if r.Header.Get("X-Concurrent") == "1" {
		if atomic.AddInt32(&arrivals, 1) == 2 {
			close(ready)
		}

		select {
		case <-ready:
		case <-time.After(5 * time.Second):
			http.Error(w, "concurrent request did not arrive", http.StatusGatewayTimeout)
			return
		}
	}

	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	w.Header().Set("X-Pid", strconv.Itoa(os.Getpid()))
	w.Header().Set("Content-Length", strconv.Itoa(len(body)))
	w.Write(body)
}

func main() {
	http.HandleFunc("/", handler)
	worker.ListenAndServe(":8080", nil)
}
