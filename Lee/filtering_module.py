# file name: filtering_module.py

import statistics       # 중간값 계산을 위한 모듈

# 속도 제한 필터 (Speed Limiter / Clamping)
def speed_limit_filter(input_speed, max_limit=0.8):
    if input_speed > max_limit:		# 1. 전진(양수) 제한
        return max_limit
    elif input_speed < -max_limit:		# 2. 후진(음수) 제한
        return -max_limit

    return input_speed				# 3. 안전 범위 안이면 그대로 통과


# 속도 변화율 제한 필터 (Rate Limiter)
def rate_limit_filter(target_speed, current_speed, max_change=0.1):
    speed_diff = target_speed - current_speed
    
    if abs(speed_diff) > max_change:
        if speed_diff > 0:
            return current_speed + max_change
        else:
            return current_speed - max_change

    return target_speed

# 저역통과 필터 (Low-Pass Filter)
def low_pass_filter(target_speed, current_speed, alpha=0.3):
      
    # 공식: (목표값 * alpha) + (이전값 * (1 - alpha))
    filtered_speed = (target_speed * alpha) + (current_speed * (1 - alpha))
    
    return filtered_speed

# 이동 평균 ( Moving Average Filter )
def moving_average_filter(data_list, new_data, window_size=5):
    data_list.append(new_data)
    if len(data_list) > window_size:    # 오래된 데이터 제거
        data_list.pop(0)

    return sum(data_list) / len(data_list)    # 평균값 반환

# 중간값 ( Median Filter )
def median_filter(data_list, new_data, window_size=5):
    data_list.append(new_data)
    if len(data_list) > window_size:    # 오래된 데이터 제거
        data_list.pop(0)

    return statistics.median(data_list)    # 중간값 반환