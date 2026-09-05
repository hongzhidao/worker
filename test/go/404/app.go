package main

import (
	"io"
	"io/ioutil"
	"net/http"
	"github.com/hongzhidao/worker/go"
)

func handler(w http.ResponseWriter, r *http.Request) {
	b, e := ioutil.ReadFile("404.html")

	if e == nil {
		w.WriteHeader(http.StatusNotFound)
		io.WriteString(w, string(b))
	}
}

func main() {
	http.HandleFunc("/", handler)
	worker.ListenAndServe(":8080", nil)
}
