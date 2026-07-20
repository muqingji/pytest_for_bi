namespace py demo

service UserService {
  UserInfo get_user(1: required string user_id)
  bool delete_user(1: string user_id)
}

