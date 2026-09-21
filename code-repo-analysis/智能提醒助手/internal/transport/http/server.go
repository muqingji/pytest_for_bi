// Package http 提供本地 HTTP/JSON 触发入口（技术方案 3.4 的 transport/http）。
//
// 职责边界：报文解析、字段校验、静态令牌鉴权、接口级超时与统一错误信封；是否提醒、原因码、
// 排程时刻、幂等命中全部由 application 层用例决定，本层不复制业务规则，也不直接访问仓储。
// 报文字段与枚举以 IDL（docs/api/reminder-service.openapi.yaml）为唯一事实源。
package http

import (
	"context"
	"crypto/rand"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	nethttp "net/http"
	"strings"
	"time"

	"intelligent-reminder-assistant/internal/application/dispatch"
	"intelligent-reminder-assistant/internal/application/evaluate"
	"intelligent-reminder-assistant/internal/application/snooze"
	"intelligent-reminder-assistant/internal/transport/http/dto"
)

const (
	// 接口级硬超时预算（技术方案 4.3.1）：超时按 DEPENDENCY_TIMEOUT 处理，调用方可复用 request_id 重放。
	DefaultTimeoutEvaluate = 5 * time.Second
	DefaultTimeoutDispatch = 10 * time.Second
	DefaultTimeoutSnooze   = 2 * time.Second

	// defaultToken 是本地静态令牌的缺省值，与 IDL 示例、testenv/config.json 一致；
	// 入口只绑定回环地址，生产接入必须换成服务身份或 mTLS。
	defaultToken = "local-dev-token"
	// readHeaderTimeout 防止慢速请求头长期占用连接；入口只在回环地址监听，不额外做限流。
	readHeaderTimeout = 5 * time.Second
	// defaultShutdownTimeout 是收到退出信号后等待在途请求结束的时长。
	defaultShutdownTimeout = 5 * time.Second
	// maxIdentifierLength 是 decision_id、request_id、user_id 三个标识的最大长度（IDL：1–64 字符）。
	maxIdentifierLength = 64

	headerRequestID           = "X-Request-ID"
	codeInvalidRequest        = "INVALID_REQUEST"
	codeDependencyTimeout     = "DEPENDENCY_TIMEOUT"
	codeDependencyUnavailable = "DEPENDENCY_UNAVAILABLE"
	messageInvalidRequest     = "request validation failed"
	messageCredential         = "missing or invalid credential"
	messageNotFound           = "resource not found"
	messageInternal           = "internal error"
	messageTimeout            = "dependency timeout"
)

// randomSource 是链路 ID 的随机源；测试替换它以覆盖随机源不可用的退化分支。
var randomSource = rand.Read

// EvaluateUseCase、DispatchUseCase、SnoozeUseCase 是入口依赖的三个用例能力。
// 入口只依赖这三个方法，不依赖 application 包的具体类型，便于用桩替身做模块集成测试。
type EvaluateUseCase interface {
	Evaluate(ctx context.Context, request evaluate.Request) (evaluate.Result, error)
}

type DispatchUseCase interface {
	DispatchDue(ctx context.Context, request dispatch.Request) (dispatch.Result, error)
}

type SnoozeUseCase interface {
	Snooze(ctx context.Context, request snooze.Request) (snooze.Result, error)
}

// Config 是本地入口的运行参数；超时为零值时取接口级默认预算。
type Config struct {
	// Token 是本地静态令牌白名单的唯一取值；空串表示使用 defaultToken。
	Token           string
	TimeoutEvaluate time.Duration
	TimeoutDispatch time.Duration
	TimeoutSnooze   time.Duration
}

// Server 是本地 HTTP 入口。零值不可用：三个用例必须装配（见 cmd/reminder-service 的 -serve）。
type Server struct {
	Evaluate EvaluateUseCase
	Dispatch DispatchUseCase
	Snooze   SnoozeUseCase
	Config   Config
	// NewRequestID 生成缺省链路 ID；缺省用随机 128 位十六进制串。
	NewRequestID func() string
	// ShutdownTimeout 覆盖退出时的等待时长，仅供测试收紧。
	ShutdownTimeout time.Duration
}

// Handler 返回三个接口的路由。未匹配的路径统一返回 404 + 错误信封（IDL：404 只表示未知路由，
// 不进入业务逻辑），避免出现非 JSON 响应。
func (s Server) Handler() nethttp.Handler {
	mux := nethttp.NewServeMux()
	mux.Handle("POST /internal/v1/reminders/evaluate",
		s.transport(s.timeout(s.Config.TimeoutEvaluate, DefaultTimeoutEvaluate), nethttp.HandlerFunc(s.handleEvaluate)))
	mux.Handle("POST /internal/v1/reminders/dispatch-due",
		s.transport(s.timeout(s.Config.TimeoutDispatch, DefaultTimeoutDispatch), nethttp.HandlerFunc(s.handleDispatch)))
	mux.Handle("POST /internal/v1/reminders/{decision_id}/snooze",
		s.transport(s.timeout(s.Config.TimeoutSnooze, DefaultTimeoutSnooze), nethttp.HandlerFunc(s.handleSnooze)))
	mux.Handle("/", nethttp.HandlerFunc(s.handleNotFound))
	return mux
}

// Serve 在 addr 上启动本地入口，ctx 取消后优雅关闭。
func (s Server) Serve(ctx context.Context, addr string) error {
	listener, err := net.Listen("tcp", addr)
	if err != nil {
		return fmt.Errorf("listen %s: %w", addr, err)
	}
	return s.ServeListener(ctx, listener)
}

// ServeListener 在给定监听器上服务。抽出来是为了让模块集成测试用临时端口启动同一套装配。
func (s Server) ServeListener(ctx context.Context, listener net.Listener) error {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	server := &nethttp.Server{Handler: s.Handler(), ReadHeaderTimeout: readHeaderTimeout}
	stopped := make(chan struct{})
	go func() {
		defer close(stopped)
		<-ctx.Done()
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), s.shutdownTimeout())
		defer shutdownCancel()
		if err := server.Shutdown(shutdownCtx); err != nil {
			// 关闭超时：强制断开仍未结束的连接，不阻塞进程退出。
			_ = server.Close()
		}
	}()

	err := server.Serve(listener)
	// Serve 正常结束只可能是被 Shutdown 关闭；其他错误（如监听器被外部关闭）也要等关闭协程退出，避免 goroutine 悬挂。
	cancel()
	<-stopped
	if errors.Is(err, nethttp.ErrServerClosed) {
		return nil
	}
	return err
}

// transport 统一处理三个接口共用的入口动作：写入 X-Request-ID、校验静态令牌、派生接口级超时上下文。
// 令牌缺失或无效一律 401 且不进入业务逻辑（技术方案 4.3.1），也不写任何决策记录。
func (s Server) transport(timeout time.Duration, next nethttp.Handler) nethttp.Handler {
	return nethttp.HandlerFunc(func(w nethttp.ResponseWriter, r *nethttp.Request) {
		requestID := s.requestID(r)
		w.Header().Set(headerRequestID, requestID)
		if !s.authorized(r) {
			writeJSON(w, nethttp.StatusUnauthorized, dto.ErrorResponse{
				Code:      codeInvalidRequest,
				Message:   messageCredential,
				Retryable: false,
				RequestID: requestID,
			})
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), timeout)
		defer cancel()
		next.ServeHTTP(w, r.WithContext(context.WithValue(ctx, scopeKey{}, scope{requestID: requestID})))
	})
}

func (s Server) handleNotFound(w nethttp.ResponseWriter, r *nethttp.Request) {
	requestID := s.requestID(r)
	w.Header().Set(headerRequestID, requestID)
	writeJSON(w, nethttp.StatusNotFound, dto.ErrorResponse{
		Code:      codeInvalidRequest,
		Message:   messageNotFound,
		Retryable: false,
		RequestID: requestID,
	})
}

// authorized 校验 Authorization 头里的静态令牌；用恒定时间比较，避免用响应时间差探测令牌。
func (s Server) authorized(r *nethttp.Request) bool {
	const scheme = "Bearer "
	header := r.Header.Get("Authorization")
	if !strings.HasPrefix(header, scheme) {
		return false
	}
	return subtle.ConstantTimeCompare([]byte(strings.TrimPrefix(header, scheme)), []byte(s.token())) == 1
}

func (s Server) token() string {
	if s.Config.Token != "" {
		return s.Config.Token
	}
	return defaultToken
}

// requestID 复用调用方传入的链路 ID，缺省时生成一个（IDL：X-Request-ID 必返，回写调用方值或服务端生成值）。
func (s Server) requestID(r *nethttp.Request) string {
	if value := r.Header.Get(headerRequestID); value != "" {
		return value
	}
	if s.NewRequestID != nil {
		return s.NewRequestID()
	}
	return randomRequestID()
}

func randomRequestID() string {
	buffer := make([]byte, 16)
	if _, err := randomSource(buffer); err != nil {
		// 随机源不可用时退化为时间戳，保证响应头始终有值。
		return fmt.Sprintf("req-%d", time.Now().UTC().UnixNano())
	}
	return "req-" + hex.EncodeToString(buffer)
}

func (s Server) timeout(configured, fallback time.Duration) time.Duration {
	if configured > 0 {
		return configured
	}
	return fallback
}

func (s Server) shutdownTimeout() time.Duration {
	if s.ShutdownTimeout > 0 {
		return s.ShutdownTimeout
	}
	return defaultShutdownTimeout
}

// decodeBody 解析请求体；allowEmpty 对应 IDL 中 requestBody 可选的接口（dispatch-due 允许不带请求体）。
func decodeBody(r *nethttp.Request, target any, allowEmpty bool) error {
	if err := json.NewDecoder(r.Body).Decode(target); err != nil {
		if errors.Is(err, io.EOF) && allowEmpty {
			return nil
		}
		return err
	}
	return nil
}

// writeJSON 写出统一信封；响应体编码失败只可能来自本进程数据，写状态码后无法再改状态，因此不再追加错误响应。
func writeJSON(w nethttp.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

// scope 是入口在请求上下文里携带的链路信息。
type scope struct {
	requestID string
}

type scopeKey struct{}

func scopeFrom(ctx context.Context) scope {
	current, ok := ctx.Value(scopeKey{}).(scope)
	if !ok {
		return scope{}
	}
	return current
}

// writeValidationError 写出参数错误（400 + INVALID_REQUEST，不重试）。
func writeValidationError(w nethttp.ResponseWriter, requestID string) {
	writeJSON(w, nethttp.StatusBadRequest, dto.ErrorResponse{
		Code:      codeInvalidRequest,
		Message:   messageInvalidRequest,
		Retryable: false,
		RequestID: requestID,
	})
}

// writeDependencyError 把用例错误映射为可重试错误：超时按 DEPENDENCY_TIMEOUT（504），
// 其余按 DEPENDENCY_UNAVAILABLE（500）。响应只返回通用描述，不回传堆栈、SQL 或内部标识（4.3.1、4.3.4）。
func writeDependencyError(w nethttp.ResponseWriter, requestID string, err error) {
	if errors.Is(err, context.DeadlineExceeded) || errors.Is(err, context.Canceled) {
		writeJSON(w, nethttp.StatusGatewayTimeout, dto.ErrorResponse{
			Code:      codeDependencyTimeout,
			Message:   messageTimeout,
			Retryable: true,
			RequestID: requestID,
		})
		return
	}
	writeJSON(w, nethttp.StatusInternalServerError, dto.ErrorResponse{
		Code:      codeDependencyUnavailable,
		Message:   messageInternal,
		Retryable: true,
		RequestID: requestID,
	})
}
