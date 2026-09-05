package main

import (
	"net/http"
	"github.com/hongzhidao/worker/go"
)

func handler(w http.ResponseWriter, r *http.Request) {
	r.ParseForm()

	w.Header().Set("X-Var-1", r.Form.Get("var1"))
	w.Header().Set("X-Var-2", r.Form.Get("var2"))
	w.Header().Set("X-Var-3", r.Form.Get("var3"))
}

func main() {
	http.HandleFunc("/", handler)
	worker.ListenAndServe(":8080", nil)
}
