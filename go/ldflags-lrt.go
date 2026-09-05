//go:build linux || netbsd
// +build linux netbsd

/*
 * Copyright (C) Max Romanov
 * Copyright (C) NGINX, Inc.
 */

package worker

/*
#cgo LDFLAGS: -lrt
*/
import "C"
