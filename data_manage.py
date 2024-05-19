import os

import pandas as pd
from numpy import nan


class Reader:
    def __new__(cls):
        if not hasattr(cls, 'instance'):
            cls.instance = super(Reader, cls).__new__(cls)
            cls.instance.__initialized = False
        return cls.instance


    def __init__(self):
        if self.__initialized:
            return
        self.__initialized = True
        self.data_url = "data.xlsx"
        self.event_df = self.theme_df = self.team_df = self.member_df = None
        self.get_dfs()


    def get_dfs(self):
        excel = pd.ExcelFile(self.data_url)
        self.event_df = pd.read_excel(excel, "Event")
        self.theme_df = pd.read_excel(excel, "Theme")
        self.team_df = pd.read_excel(excel, "Team")
        self.member_df = pd.read_excel(excel, "Member")


    def is_event_name_unique(self, name: str):
        return not (name in self.event_df['event'].to_list())


    @staticmethod
    def is_digit(number: str):
        return number.isdigit()


    def add_event_theme(self, event_name, org_id, alias, max_members, file_url):
        df = pd.read_excel(file_url)
        event_hash = hash(event_name)
        add_event_df = pd.DataFrame.from_records([{
            "event": event_name,
            "organizer_id": org_id,
            "alias": alias,
            "max_members": max_members,
            "event_hash": event_hash
        }])

        errors = []
        theme = []

        if df.empty:
            errors.append(f"В файле отсутствуют данные.")
            os.remove(file_url)
            return errors

        # проверка наличия заголовков
        for col_name in ['theme', 'company', 'max_teams','responsible', 'email', 'description', 'background', 'problem', 'expected_result']:
            if col_name not in df.columns:
                errors.append(f"Отстуствует заголовок {col_name}.")
        if errors:
            os.remove(file_url)
            return errors

        for index, row in df.iterrows():
            if not self.is_digit(str(row['max_teams'])):
                errors.append(f"Ошибка в строке {index+2}: значение не является числом.\n    {row['max_teams']}")
                continue
            if len(df[df['theme'] == row['theme']]) != 1:
                errors.append(f"Ошибка в строке {index+2}: найден дубликат.\n    {row['theme']}")
                continue
            theme.append(row)
        if not errors:
            self.event_df = pd.concat([
                self.event_df,
                add_event_df
            ], ignore_index=True)
            self.event_df['event_hash'] = self.event_df['event_hash'].apply(pd.to_numeric)

            add_theme_df = pd.DataFrame.from_records(theme)
            add_theme_df['event_hash'] = event_hash
            add_theme_df['theme_hash'] = add_theme_df['theme'].apply(hash)
            self.theme_df = pd.concat([
                self.theme_df,
                add_theme_df
            ], ignore_index=True)
            self.theme_df[['event_hash', 'theme_hash']] = self.theme_df[['event_hash', 'theme_hash']].apply(pd.to_numeric)
        os.remove(file_url)
        return errors


    def get_events(self):
        return self.event_df[["event", "event_hash"]].to_dict('records')


    def get_event_name(self, event_hash):
        return self.event_df[self.event_df['event_hash']==event_hash]['event'].iloc[0]


    def get_themes_to_create(self, leader_id, event_hash):
        if not self.member_df[
            (self.member_df['member_id'] == leader_id) & (self.member_df["event_hash"] == event_hash) & (self.member_df['accepted'])
        ].empty:
            return 1
        teams_on_theme_count = self.team_df[self.team_df["event_hash"] == event_hash]["theme_hash"].value_counts()
        themes_of_event_df = self.theme_df[self.theme_df["event_hash"] == event_hash]
        teams_in_themes = pd.merge(themes_of_event_df, teams_on_theme_count, how='outer', left_on='theme_hash', right_on='theme_hash').fillna(0)
        return teams_in_themes[teams_in_themes["max_teams"] > teams_in_themes["count"]][["theme", "theme_hash"]].to_dict('records')

    
    def theme_info(self, event_hash, theme_hash):
        row = self.theme_df[(self.theme_df["event_hash"] == event_hash) & (self.theme_df["theme_hash"] == theme_hash)].copy()
        row.rename(columns={"event_hash": "event"}, inplace=True)
        row['event'] = self.get_event_name(event_hash)
        return row.replace({nan: None}).to_dict('records')[0]
    

    def is_create_theme_available(self, leader_id, event_hash, theme_hash):
        if not self.member_df[
            (self.member_df['member_id'] == leader_id) & (self.member_df["event_hash"] == event_hash) & (self.member_df['accepted'])
        ].empty:
            return False
        teams_count = len(self.team_df[(self.team_df["event_hash"] == event_hash) & (self.team_df["theme_hash"] == theme_hash)])
        max_teams = self.theme_df[(self.theme_df["event_hash"] == event_hash) & (self.theme_df["theme_hash"] == theme_hash)].iloc[0, 3]

        return teams_count < max_teams
    

    def get_theme_name(self, event_hash, theme_hash):
        return self.theme_df[(self.theme_df['event_hash']==event_hash) & (self.theme_df['theme_hash']==theme_hash)]['theme'].iloc[0]


    def is_team_name_unique(self, event_hash, team_name):
        return self.team_df[(self.team_df['event_hash'] == event_hash) & (self.team_df['team_name'] == team_name)].empty


    def add_team(self, event_hash, theme_hash, team_name, leader_id, l_alias, description):
        team_hash = hash(team_name)
        add_team_df = pd.DataFrame.from_records([{
            "event_hash": event_hash,
            "theme_hash": theme_hash,
            "team_name": team_name,
            "leader_id": leader_id,
            "leader_alias": l_alias,
            "team_opened": True,
            "team_needs": description,
            "team_hash": team_hash
        }])

        self.team_df = pd.concat([
            self.team_df,
            add_team_df
        ], ignore_index=True)

        add_member_df = pd.DataFrame.from_records([{
            "member_id": leader_id,
            "alias": l_alias,
            "event_hash": event_hash,
            "team_hash": team_hash,
            "accepted": True
        }])

        self.member_df = pd.concat([
            self.member_df,
            add_member_df
        ], ignore_index=True)


    def get_themes_to_join(self, member_id, event_hash):
        if not self.member_df[
            (self.member_df['member_id'] == member_id) & (self.member_df["event_hash"] == event_hash) & (self.member_df['accepted'] == True)
        ].empty:
            return 1

        teams_with_member = self.member_df[(self.member_df["member_id"] == member_id)]["team_hash"].tolist()
        max_members = self.event_df[self.event_df['event_hash'] == event_hash].iloc[0, 3]
        members_in_team_count = self.member_df[(self.member_df["event_hash"] == event_hash) &
                                               (self.member_df["accepted"] == True)]["team_hash"].value_counts()
        team_hashes = members_in_team_count[members_in_team_count < max_members].index.tolist()
        teams_to_join = self.team_df[(self.team_df['team_opened'] == True) & 
                                     (self.team_df['team_hash'].isin(team_hashes)) &
                                     (~self.team_df['team_hash'].isin(teams_with_member))]
        themes_to_join = self.theme_df[self.theme_df["theme_hash"].isin(teams_to_join['theme_hash'])]
        return themes_to_join[["theme", "theme_hash"]].to_dict('records')
    

    def get_teams_to_join(self, leader_id, event_hash, theme_hash):
        if not self.member_df[
            (self.member_df['member_id'] == leader_id) & (self.member_df["event_hash"] == event_hash) & (self.member_df['accepted'])
        ].empty:
            return 1
        
        max_members = self.event_df[self.event_df['event_hash'] == event_hash].iloc[0, 3]
        members_in_team_count = self.member_df[self.member_df["event_hash"] == event_hash]["team_hash"].value_counts()
        team_hashes = members_in_team_count[members_in_team_count < max_members].index.tolist()
        teams_to_join = self.team_df[(self.team_df['event_hash'] == event_hash) &
                                     (self.team_df['theme_hash'] == theme_hash) & 
                                     (self.team_df['team_opened'] == True) & 
                                     (self.team_df['team_hash'].isin(team_hashes))]

        return teams_to_join[['team_name', 'team_hash']].to_dict('records')


    def get_team_description(self, event_hash, team_hash):
        return self.team_df[(self.team_df["event_hash"] == event_hash) & 
                            (self.team_df['team_hash'] == team_hash)].to_dict("records")[0]['team_needs']
    

    def get_team_name(self, event_hash, team_hash):
        return self.team_df[(self.team_df["event_hash"] == event_hash) & 
                            (self.team_df['team_hash'] == team_hash)].to_dict("records")[0]['team_name']


    def add_member_to_team(self, member_id, member_alias, event_hash, team_hash):
        if not self.member_df[
            (self.member_df['member_id'] == member_id) & (self.member_df["event_hash"] == event_hash) & (self.member_df['accepted'] == True)
        ].empty:
            return 1
        
        max_members = self.event_df[self.event_df['event_hash'] == event_hash].iloc[0, 3]
        if ((self.team_df[(self.team_df['team_hash'] == team_hash) & 
                          (self.member_df['event_hash'] == event_hash)].iloc[0, 5] == False) or 
            (len(self.member_df[(self.member_df['team_hash'] == team_hash) & 
                                (self.member_df['accepted'] == True) &
                                (self.member_df['event_hash'] == event_hash)]) >= max_members)):
            return 2

        add_member_df = pd.DataFrame.from_records([{
            "member_id": member_id,
            "alias": member_alias,
            "event_hash": event_hash,
            "team_hash": team_hash,
            "accepted": False
        }])
        
        self.member_df = pd.concat([
            self.member_df,
            add_member_df
        ], ignore_index=True)

        leader_data = self.team_df[(self.team_df['team_hash'] == team_hash) & (self.team_df['event_hash'] == event_hash)].to_dict("records")[0]
        return {"leader_id": leader_data["leader_id"], "leader_alias": leader_data['leader_alias'], "team_name": leader_data['team_name']}


    def get_member_events(self, member_id):
        rows_with_member = self.member_df[(self.member_df['member_id'] == member_id) & (self.member_df['accepted'] == True)]
        return self.event_df[self.event_df['event_hash']
                             .isin(rows_with_member['event_hash'])][['event', 'event_hash']].to_dict('records')
    

    def get_team_info(self, member_id, event_hash):
        team_hash = self.member_df[(self.member_df['member_id'] == member_id) & 
                                   (self.member_df['accepted'] == True) &
                                   (self.member_df['event_hash'] == event_hash)].iloc[0, 3]
        return self.team_df[(self.team_df['team_hash'] == team_hash) & (self.team_df['event_hash'] == event_hash)].to_dict('records')[0]
    

    def get_max_members(self, event_hash):
        return self.event_df[self.event_df['event_hash'] == event_hash].to_dict("records")[0]['max_members']
    

    def get_current_members(self, event_hash, team_hash):
        return len(self.member_df[(self.member_df['event_hash'] == event_hash) & 
                                  (self.member_df['team_hash'] == team_hash) &
                                  (self.member_df['accepted'] == True)])


    def get_not_accepted_members(self, event_hash, team_hash):
        not_accepted = self.member_df[(self.member_df['event_hash'] == event_hash) &
                                      (self.member_df['team_hash'] == team_hash) & 
                                      (self.member_df['accepted'] == False)]
        return not_accepted[['member_id', 'alias']].to_dict("records")
    

    def get_user_alias(self, member_id):
        return self.member_df[(self.member_df['member_id'] == member_id)].iloc[0, 1]


    def accept_member(self, event_hash, team_hash, member_id):
        max_members = self.get_max_members(event_hash)
        cur_members = self.get_current_members(event_hash, team_hash)
        if max_members == cur_members:
            return 1

        condition = (self.member_df['event_hash'] == event_hash) & (self.member_df['team_hash'] == team_hash) & (self.member_df['member_id'] == member_id)

        if len(self.member_df[condition]) == 0:
            return 2

        self.member_df.loc[condition, 'accepted'] = True

        rows_to_delete = self.member_df[(self.member_df['event_hash'] == event_hash) & 
                (self.member_df['member_id'] == member_id) &
                (self.member_df['accepted'] == False)].index
        self.member_df.drop(index=rows_to_delete, inplace=True)

        return [max_members, cur_members+1]


    def remove_member(self, event_hash, team_hash, member_id):
        rows_to_delete = self.member_df[(self.member_df['event_hash'] == event_hash) & 
                (self.member_df['team_hash'] == team_hash) &
                (self.member_df['member_id'] == member_id)].index
        self.member_df.drop(index=rows_to_delete, inplace=True)


    def flip_team_opened(self, event_hash, team_hash):
        condition = (self.team_df['event_hash'] == event_hash) & (self.team_df['team_hash'] == team_hash)
        self.team_df.loc[condition, 'team_opened'] = not self.team_df.loc[condition, 'team_opened'].iloc[0]


    def get_team_members(self, leader_id, event_hash, team_hash):
        return self.member_df[(self.member_df['event_hash'] == event_hash) &
                              (self.member_df['team_hash'] == team_hash) &
                              (self.member_df['accepted'] == True) &
                              (self.member_df['member_id'] != leader_id)][['member_id', 'alias']].to_dict('records')
    

    def change_team_needs(self, event_hash, team_hash, description):
        self.team_df.loc[(self.team_df['event_hash'] == event_hash) &
                              (self.team_df['team_hash'] == team_hash), 'team_needs'] = description
        

    def delete_team(self, event_hash, team_hash, leader_id):
        members_deleted = self.member_df[(self.member_df['event_hash'] == event_hash) &
                              (self.member_df['team_hash'] == team_hash) &
                              (self.member_df['accepted'] == True) &
                              (self.member_df['member_id'] != leader_id)]['member_id'].to_list()
        
        rows_to_delete = self.member_df[(self.member_df['event_hash'] == event_hash) & 
                (self.member_df['team_hash'] == team_hash)].index
        self.member_df.drop(index=rows_to_delete, inplace=True)

        team_row = self.team_df[(self.team_df['event_hash'] == event_hash) & 
                (self.team_df['team_hash'] == team_hash)].index
        self.team_df.drop(index=team_row, inplace=True)

        return members_deleted
    

    def get_leader_id(self, event_hash, team_hash):
        return self.team_df.loc[(self.team_df['event_hash'] == event_hash) & 
                (self.team_df['team_hash'] == team_hash), 'leader_id'].iloc[0]
    

    def get_all_themes(self, event_hash):
        return self.theme_df[self.theme_df['event_hash'] == event_hash][["theme", "theme_hash"]].to_dict('records')
    

    def get_user_events(self, organizer_id):
        return self.event_df[self.event_df['organizer_id'] == organizer_id][["event", "event_hash"]].to_dict('records')


    def delete_event(self, event_hash):
        members_to_delete = self.member_df[(self.member_df['event_hash'] == event_hash)].index
        self.member_df.drop(index=members_to_delete, inplace=True)

        teams_to_delete = self.team_df[(self.team_df['event_hash'] == event_hash)].index
        self.team_df.drop(index=teams_to_delete, inplace=True)

        themes_to_delete = self.theme_df[(self.theme_df['event_hash'] == event_hash)].index
        self.theme_df.drop(index=themes_to_delete, inplace=True)

        event_to_delete = self.event_df[(self.event_df['event_hash'] == event_hash)].index
        self.event_df.drop(index=event_to_delete, inplace=True)


    def save_data(self):
        with pd.ExcelWriter(self.data_url) as writer:
            self.event_df.to_excel(writer, "Event", index=False)
            self.theme_df.to_excel(writer, "Theme", index=False)
            self.team_df.to_excel(writer, "Team", index=False)
            self.member_df.to_excel(writer, "Member", index=False)
