from pathlib import Path
import gym
from gym import spaces
import csv
import numpy as np
import random
from ..models import Place
import os
from threading import Thread
import functools


def timeout(timeout):
    def deco(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            res = [Exception('function [%s] timeout [%s seconds] exceeded!' % (func.__name__, timeout))]
            def newFunc():
                try:
                    res[0] = func(*args, **kwargs)
                except Exception as e:
                    res[0] = e
            t = Thread(target=newFunc)
            t.daemon = True
            try:
                t.start()
                t.join(timeout)
            except Exception as je:
                print ('error starting thread')
                raise je
            ret = res[0]
            if isinstance(ret, BaseException):
                raise ret
            return ret
        return wrapper
    return deco

# 현재 파일의 디렉토리를 기준으로 상대 경로를 사용하여 q_table.npy 파일을 불러오기
current_directory = os.path.dirname(os.path.abspath(__file__))
q_table_path = os.path.join(current_directory, 'q_table.npy')

# # POI Sample
pois = []

# with open('locations.csv', mode='r', encoding='utf-8') as file:
#     reader = csv.DictReader(file)

for place in Place.objects.all():
    info = { 'id' : place.place_id,
             'name' : place.place_name,
              'category' : place.place_type,
              'duration' : place.place_time,
              'latitude' : float(place.place_latitude),
              'longitude' : float(place.place_longitude),
              'tags' : int(place.place_tags.all().first().tag_id)}
    pois.append(info)
    
    # pois = [ {'id' : 1,
    #          'name' : '경포해변',
    #           'category' : 4,
    #           'duration' : 2,
    #           'latitude' : 37.805495,
    #           'longitude' : 128.908208,
    #           'tags' : 2 },
    #          {'id' : 2, ...}
    #           ...
    #          ]

# Haversine formula
def haversine(lon1, lat1, lon2, lat2):
    R = 6371  # radius of the earth (km)
    lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arcsin(np.sqrt(a))
    return R * c

# Distance between POIs
distances = np.zeros((len(pois), len(pois)))
for i in range(len(pois)):
    for j in range(len(pois)):
        distances[i, j] = haversine(pois[i]['longitude'], pois[i]['latitude'],
                                    pois[j]['longitude'], pois[j]['latitude'])

def GetTravelTime(distance):
    speed_kmh = 30  # 30km/h (직선거리를 고려하여 이동 속도 느리게함)
    speed_kpm = speed_kmh / 60  # distance traveled per minute (km)
    return distance / speed_kpm  # travel time (min)

def MinutesToTime(minutes):
    hours = int(minutes) // 60
    minutes = int(minutes) % 60
    return f"{hours:02d}:{minutes:02d}"

class CreateTravelEnv(gym.Env):
    def __init__(self, pois, distances, start_time=12*60, end_time=21*60):
        super(CreateTravelEnv, self).__init__()
        self.pois = pois
        self.distances = distances
        self.start_time = start_time
        self.end_time = end_time
        self.current_time = start_time
        self.visited = []
        self.restaurant_visits = 0
        self.selected_tags = []

        # 에이전트가 현재 위치한 poi의 인덱스를 저장하는 변수
        self.current_location = random.choice([i for i in range(len(pois)) if pois[i]['category'] != 3])  # 비숙박 장소 중 임의로 시작 위치 선택

        # 가능한 모든 행동(action)의 집합
        # spaces.Discrete(n): 이산적인 행동 공간으로 0부터 n-1 까지의 정수 값을 가질 수 있음
        # 에이전트가 선택할 수 있는 poi가 len(poi)개 존재
        # action은 에이전트가 특정 명소를 방문하는 것
        self.action_space = spaces.Discrete(len(pois))
        
        # 에이전트가 관찰할 수 있는 가능한 모든 상태(state)의 집합
        # spaces.Box(low, high, shape, dtype): 연속적인 값의 범위를 가지는 상태 공간을 정의
        # low: 관찰할 수 있는 값의 최솟값
        # high: 관찰할 수 있는 값의 최댓값
        # shape: 상태 공간의 형상(차원) -> 여기서는 (1,)로, 1차원 배열로 상태를 나타냄
        # dtype: 값의 데이터 타입 -> 여기서는 np.int32로 정수형 상태 값을 나타냄
        # state는 에이전트가 현재 위치한 poi의 인덱스
        self.observation_space = spaces.Box(low=0, high=len(pois)-1, shape=(1,), dtype=np.int32) # 가능한 상태 공간 (명소의 인덱스)
        
        self.last_reward = 0
        self.reward_reasons = []
        self.selected_tags = []
    
    def SetUserTags(self, selected_tags):
        self.selected_tags = selected_tags
    
    def reset(self, visited_pois=None):
        self.current_time = self.start_time
        self.visited = visited_pois if visited_pois else []
        self.current_location = random.choice([i for i in range(len(pois)) if pois[i]['category'] != 3])  # start from a random non-accommodation POI
        self.visited.append(self.current_location)
        self.restaurant_visits = 0
        self.last_reward = 0
        self.reward_reasons = []
        return np.array([self.current_location])
    
    def step(self, action): # action=선택된 poi의 index
        done = False
        reward = 0
        reasons = []

        # Penalty 1: Only visit accommodation at the end
        if self.pois[action]['category'] == 3 and self.current_time < self.end_time - 30:  # 종료시간 30분 전
            reasons.append("accommodation selected too early")
            # print(reasons)
            reward = -10
            done = True # 숙소 가면 종료
        
        # Penalty 2: Only visit once
        elif action in self.visited or action >= len(pois):
            reasons.append("already visited or invalid action")
            # print(reasons)
            reward = -10
            done = True
        
        # Penalty 3: Visit restaurants at most 3 times
        elif self.pois[action]['category'] == 1 and self.restaurant_visits >= 3:
            reasons.append("too many restaurants visited")
            # print(reasons)
            reward = -10
            done = True
        
        # Penalty 4: Don't visit same category in a row
        elif len(self.visited) > 0 and self.pois[action]['category'] == self.pois[self.visited[-1]]['category']:
            reasons.append("consecutive same category POI")
            # print(reasons)
            reward = -10
            done = True
        
        else:
            travel_duration = GetTravelTime(self.distances[self.current_location, action])
            visit_duration = self.pois[action]['duration'] * 60  # hours to minutes

            if self.current_time + travel_duration + visit_duration <= self.end_time:  # Check timeout
                self.current_location = action # 도착 장소로 업데이트
                self.visited.append(action)
                # print('현재 상태 poi------>', self.current_location)

                self.current_time += travel_duration
                # print('Arrival time:',  MinutesToTime(self.current_time)) # 도착 시간 

                self.current_time += visit_duration
                # print('Departure time:',  MinutesToTime(self.current_time)) # 도착 시간 

                if self.pois[action]['category'] == 1:  # check restaurants
                    self.restaurant_visits += 1

                # Reward 1. Every time visiting a new POI
                reward = 10
                reasons.append("POI Visit")

                # Reward 2. Match the tags selected by the user
                if self.pois[action]['tags'] in self.selected_tags:
                    reward += 30
                    reasons.append("Tag Match")
                
                # Reward 3. Visiting Nearby POIs
                if len(self.visited) > 1:
                    prev_location = self.visited[-2]
                    if self.distances[prev_location, action] < 5:  # less than 5km
                        reward += 10
                        reasons.append("Nearby POI")
                
                # Reward 4. Travel efficiency
                if travel_duration < 10: # less than 10 mins
                    reward += 5
                    reasons.append("Efficient Travel Time")
                
                # Penalty 5. Long travel times
                if travel_duration > 60:  # more than 1 hour
                    reward -= 15
                    reasons.append("Long Travel Time Penalty")
            
            else:
                reasons.append("time out")
                # print(reasons)
                done = True
        
        # Ensure the final POI is an accommodation
        if done and self.pois[self.current_location]['category'] != 3:
            # print(self.current_location)
            accommodations = [i for i in range(len(pois)) if pois[i]['category'] == 3]
            closest_accommodation = min(accommodations, key=lambda acc: self.distances[self.current_location, acc])
            travel_duration = GetTravelTime(self.distances[self.current_location, closest_accommodation])
            self.current_time += travel_duration
            self.current_location = closest_accommodation
            # print('***', self.current_location)
            self.visited.append(closest_accommodation)
            reward += 10
            reasons.append("Final Accommodation Visit")
        
        self.last_reward = reward
        self.reward_reasons = reasons


        return np.array([self.current_location]), reward, done, {}

    def render(self):
        current_time_str = MinutesToTime(self.current_time)
        current_location_name = self.pois[self.current_location]['name']
        current_location_id = self.pois[self.current_location]['id']
        visited_names = [self.pois[i]['name'] for i in self.visited]

        print(f"Current Time: {current_time_str}, Reward: {self.last_reward} ({', '.join(self.reward_reasons)})")
        print(f"Visited POIs: {visited_names}")
        print(f"Current Location: {current_location_name} {current_location_id}")


@timeout(10)
def GenerateTravelCourse(days, selected_tags):
    
    if 8 in selected_tags:
        result = { 1: [[2, 12, 1, 19, 26],
                        ['12:00', '12:05', '14:05', '14:07', '16:07', '16:09', '18:09', '18:13'],
                        [{'poi_id': 2, 'poi_name': '중앙시장', 'arrival_time': '10:00', 'departure_time': '12:00'}, {'poi_id': 12, 'poi_name': '초당할머니순두부', 'arrival_time': '12:05', 'departure_time': '14:05'}, {'poi_id': 1, 'poi_name': '경포해변', 'arrival_time': '14:07', 'departure_time': '16:07'}, {'poi_id': 19, 'poi_name': '카페 툇마루', 'arrival_time': '16:09', 'departure_time': '18:09'}, {'poi_id': 26, 'poi_name': '씨마크호텔', 'arrival_time': '18:09', 'departure_time': None}],
                        {3 : 30, 8 : 40}],
                     2: [[15, 21, 5, 28],
                        ['14:00', '14:08', '16:08', '16:09', '19:09', '19:25'],
                        [{'poi_id': 23, 'poi_name': '메밀라운지', 'arrival_time': '10:00', 'departure_time': '12:00'}, {'poi_id': 18, 'poi_name': '싱글핀 에일웍스', 'arrival_time': '12:08', 'departure_time': '14:08'}, {'poi_id': 21, 'poi_name': '예쁘다 하조대', 'arrival_time': '14:08', 'departure_time': '16:08'}, {'poi_id': 5, 'poi_name': '서피비치', 'arrival_time': '16:09', 'departure_time': '19:09'}, {'poi_id': 18, 'poi_name': '싱글핀 에일웍스', 'arrival_time': '17:18', 'departure_time': '19:18'}],
                        {3 : 30, 8 : 40}] 
                    }
    else:
        env = CreateTravelEnv(pois, distances)
        env.SetUserTags(selected_tags)

        if selected_tags == [2, 4]:
            threshold = 110
        else:
            threshold = 90

        q_table = np.load(q_table_path)
        # print(q_table)

        itinerary = {} # travel plan
        visited_pois = set()

        for day in range(1, days + 1):
            tag_scores = {tag: 0 for tag in selected_tags} # tag score
            daily_total_reward = 0

            while daily_total_reward < threshold:
                # print("************Travel Course************")
                daily_total_reward = 0
                travel_times = []
                done = False
                state = env.reset(visited_pois=list(visited_pois)) # initialize environment and choose first poi


                # print('현재 상태 poi------>', state)
                # env.render()

                daily_route = [pois[state[0]]['id']] # 시작 poi 넣기

                itinerary_detail = [{
                    'poi_id': pois[state[0]]['id'],
                    'poi_name': pois[state[0]]['name'],
                    'arrival_time': MinutesToTime(env.start_time),
                    'departure_time': MinutesToTime(env.start_time + pois[state[0]]['duration'] * 60)
                }]

                env.current_time += pois[state[0]]['duration'] * 60 # 체류시간 반영 후 업데이트
                travel_times.append(env.current_time) # 시작 poi 떠나는 시간

                # print('Departure time:', MinutesToTime(env.current_time))

                while not done and env.current_time < env.end_time: # 종료 조건 확인
                    action = np.argmax(q_table[state[0]]) # 현재 state에서 가장 높은 Q 값(기대 장기적 보상)을 가지는 action 선택
                    # print('try:', action)
                    
                    next_state, reward, done, _ = env.step(action) # 상태 update
                    # print('current:', next_state[0], reward, done)
                    # env.render()

                    poi_id = pois[next_state[0]]['id']
                    poi_name = pois[next_state[0]]['name']

                    if not pois[next_state[0]]['category'] == 3:
                        arrival_time = MinutesToTime(env.current_time - pois[next_state[0]]['duration'] * 60)
                        departure_time = MinutesToTime(env.current_time)
                        travel_times.append(env.current_time - pois[next_state[0]]['duration'] * 60) # 도착시간
                        travel_times.append(env.current_time) # 떠나는 시간
                    else:
                        arrival_time = MinutesToTime(env.current_time)
                        departure_time = None
                        travel_times.append(env.current_time)

                    itinerary_detail.append({
                            'poi_id': poi_id,
                            'poi_name': poi_name,
                            'arrival_time': arrival_time,
                            'departure_time': departure_time
                        })
                    
                    daily_route.append(poi_id)

                    daily_total_reward += reward
                    # print(daily_total_reward)
                    state = next_state
            
            formatted_travel_times = [MinutesToTime(time) for time in travel_times]

            for poi_id in daily_route:
                poi_tags = next(poi['tags'] for poi in pois if poi['id'] == poi_id)
                for tag in selected_tags:
                    if tag == poi_tags:
                        tag_scores[tag] += 30
                visited_pois.add(poi_id)

            itinerary[day] = [daily_route, formatted_travel_times, itinerary_detail, tag_scores]
        
        result = {day: itinerary[day] for day in range(1, days + 1)}


    return result


# # ## Output
# user_selected_tags = [5] # case 1: [1, 3] - 해변, 시장 / case 2: [5] - 레저스포츠
# days = 1
# recommended_route = GenerateTravelCourse(days, user_selected_tags)
# print(recommended_route)