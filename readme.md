**/voucher/create**

Create a voucher. 

Params:

- `user_id`
- `amount`
- `token`

Example:
```bash
echo '{"user_id":"DISCORD USER ID","amount":COLACOIN AMOUNT,"token":"APP TOKEN"}' | http POST endpoint/voucher/create --json
```
**/voucher/redeem**

Redeem a voucher. 

Params:

- `user_id`
- `voucher_id`
- `token`

Example:
```bash
echo '{"user_id":"DISCORD USER ID","voucher_id":"VOUCHER ID","token":"APP TOKEN"}' | http POST endpoint/voucher/redeem --json
```
**/get_user**

Get info on a user

Params:
- `user_id`
- `token`

Example:
```bash
echo '{"user_id":USER ID,"token":"TOKEN"}' | http POST endpoint/get_user --json
```
**/get_top**

Get all user sorted in order of wealth

Params:
- `token`

Example:
```bash
echo '{"token":"TOKEN"}' | http POST
endpoint/get_top --json
```
