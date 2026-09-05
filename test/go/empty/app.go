package main

import (
	"net/http"
	"github.com/hongzhidao/worker/go"
)

func handler(w http.ResponseWriter, r *http.Request) {}

func main() {
	http.HandleFunc("/", handler)
	worker.ListenAndServe(":8080", nil)
}
