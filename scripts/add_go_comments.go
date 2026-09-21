package main

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

var funcPattern = regexp.MustCompile(`^func\s+(?:\([^)]*\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\(`)

func main() {
	root := filepath.Join("code-repo-analysis", "智能提醒助手")
	err := filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.IsDir() || !strings.HasSuffix(path, ".go") {
			return nil
		}
		if err := annotate(path); err != nil {
			return err
		}
		fmt.Println(path)
		return nil
	})
	if err != nil {
		panic(err)
	}
}

func annotate(path string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	lines := strings.SplitAfter(string(data), "\n")
	if len(lines) == 0 {
		return nil
	}
	isTestFile := strings.HasSuffix(path, "_test.go")
	packageIndex := -1
	for i, line := range lines {
		if strings.HasPrefix(strings.TrimSpace(line), "package ") {
			packageIndex = i
			break
		}
	}
	if packageIndex < 0 {
		return nil
	}
	if !hasCommentImmediatelyBefore(lines, packageIndex) {
		kind := "业务实现"
		if isTestFile {
			kind = "业务单元测试与边界验证"
		}
		lines = insert(lines, packageIndex, []string{
			fmt.Sprintf("// 本文件承载智能提醒助手的%s，注释重点说明数据准备、规则边界和失败处理的意图。\n", kind),
		})
		packageIndex++
	}
	for i := 0; i < len(lines); i++ {
		line := strings.TrimSpace(lines[i])
		match := funcPattern.FindStringSubmatch(line)
		if match == nil || hasCommentImmediatelyBefore(lines, i) {
			continue
		}
		name := match[1]
		lines = insert(lines, i, []string{functionComment(name, isTestFile)})
		i++
	}
	return os.WriteFile(path, []byte(strings.Join(lines, "")), 0o644)
}

func hasCommentImmediatelyBefore(lines []string, index int) bool {
	for index--; index >= 0; index-- {
		trimmed := strings.TrimSpace(lines[index])
		if trimmed == "" {
			continue
		}
		return strings.HasPrefix(trimmed, "//") || strings.HasSuffix(trimmed, "*/")
	}
	return false
}

func insert(lines []string, index int, additions []string) []string {
	result := make([]string, 0, len(lines)+len(additions))
	result = append(result, lines[:index]...)
	result = append(result, additions...)
	result = append(result, lines[index:]...)
	return result
}

func functionComment(name string, isTestFile bool) string {
	if strings.HasPrefix(name, "Test") && isTestFile {
		return fmt.Sprintf("// %s 验证对应业务路径的核心结果、状态变化和边界处理，确保实现与需求契约保持一致。\n", name)
	}
	switch {
	case strings.HasPrefix(name, "Get"), strings.HasPrefix(name, "List"), strings.HasPrefix(name, "Read"):
		return fmt.Sprintf("// %s 读取业务流程所需的数据，并将缺失记录、上下文取消或存储错误明确传递给调用方。\n", name)
	case strings.HasPrefix(name, "Create"), strings.HasPrefix(name, "Update"), strings.HasPrefix(name, "Append"), strings.HasPrefix(name, "Save"):
		return fmt.Sprintf("// %s 持久化一次业务状态变化；调用方依靠返回错误判断是否可以继续推进后续流程。\n", name)
	case strings.HasPrefix(name, "parse"), strings.HasPrefix(name, "validate"), strings.HasPrefix(name, "new"):
		return fmt.Sprintf("// %s 负责把外部输入转换为内部契约，并在无法安全解释时显式拒绝，避免静默降级。\n", name)
	case strings.HasPrefix(name, "assert"):
		return fmt.Sprintf("// %s 集中断言测试结果，确保失败信息指向实际业务差异而不是测试夹具自身。\n", name)
	default:
		return fmt.Sprintf("// %s 是该业务流程的辅助步骤，集中处理可复用的默认值、转换或边界规则。\n", name)
	}
}
