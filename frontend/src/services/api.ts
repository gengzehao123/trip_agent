import axios from 'axios'
import type {
  ConversationResponse,
  TripFormData,
  TripTaskCreateResponse,
  TaskStatusResponse
} from '@/types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000, // 2分钟超时
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
apiClient.interceptors.request.use(
  (config) => {
    console.log('发送请求:', config.method?.toUpperCase(), config.url)
    return config
  },
  (error) => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => {
    console.log('收到响应:', response.status, response.config.url)
    return response
  },
  (error) => {
    console.error('响应错误:', error.response?.status, error.message)
    return Promise.reject(error)
  }
)

/**
 * 创建旅行规划任务（返回 task_id）
 */
export async function createTripTask(formData: TripFormData): Promise<TripTaskCreateResponse> {
  try {
    const response = await apiClient.post<TripTaskCreateResponse>('/api/trip/plan', formData)
    return response.data
  } catch (error: any) {
    console.error('创建旅行规划任务失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '创建旅行规划任务失败')
  }
}

/**
 * 查询旅行规划任务状态（含真实进度）
 */
export async function getTaskStatus(taskId: string): Promise<TaskStatusResponse> {
  try {
    const response = await apiClient.get<TaskStatusResponse>(`/api/trip/tasks/${taskId}`)
    return response.data
  } catch (error: any) {
    console.error('查询任务状态失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '查询任务状态失败')
  }
}

/**
 * 查询会话上下文
 */
export async function getConversation(sessionId: string): Promise<ConversationResponse> {
  try {
    const response = await apiClient.get<ConversationResponse>(`/api/conversations/${sessionId}`)
    return response.data
  } catch (error: any) {
    throw new Error(error.response?.data?.detail || error.message || '查询会话失败')
  }
}

/**
 * 提交自然语言行程修改任务
 */
export async function reviseTrip(
  sessionId: string,
  content: string
): Promise<TripTaskCreateResponse> {
  try {
    const response = await apiClient.post<TripTaskCreateResponse>(
      `/api/conversations/${sessionId}/messages`,
      { content }
    )
    return response.data
  } catch (error: any) {
    throw new Error(error.response?.data?.detail || error.message || '提交行程修改失败')
  }
}

/**
 * 健康检查
 */
export async function healthCheck(): Promise<any> {
  try {
    const response = await apiClient.get('/health')
    return response.data
  } catch (error: any) {
    console.error('健康检查失败:', error)
    throw new Error(error.message || '健康检查失败')
  }
}

export default apiClient
