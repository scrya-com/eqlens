"""The small mark in the corner of a card, and where it leads.

The Scrya logo at 60 px (shown at 30), white on nothing, so it sits on any dark
card and carries no color of its own. It is inside the SVG as data, so a
drawing never fetches anything from the network.
"""

URL = "https://scrya.com/eqlens"
SIZE = 22.5  # points: 30 px at the SVG's natural size
LOGO_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAADwAAAA8CAYAAAA6/NlyAAAHzElEQVR42u2ba4xcZRnHf+fM7M7MlpZ2uy1atOUilGtJgzSIilou"
    "giEmQpSLYtDUywdiSEyKhmKiRsAPVDES1FZRERCC8YJp1KRBKpKWS6iFSgAJTWhKWmi73e12u7ud/fPB/4lPTmbK7M7ZtrFzkjfn"
    "vOd9z3mf/3N/nzOTSOJoOlKOsqMDuAO4A7gDuAP4SD7Kh2HNJNfX/xvgNICsNwCYBE0TMD6l3J7CTKtk4vMLzACqvh5yyz83ZcCn"
    "AnCaI/ZMYCnwUeAsoA/o8dgA8AbwDPA48Biw9R0YdkQBLlltE+BK4CbgQ0GaLwPbgD0G0wecDJziOaPAg8BdwHO5dxZzSCqiJZJS"
    "X58v6Qn99xiQ9GNJF0nqPcizcyV9RtIa/e9YLWme55QKopOiwGbXy03smKRbJfU1mFuS1C3pWEnzJZ0t6TRJZc85XdIjfs9WSZcX"
    "CboIsImJXW0i10k6I8wpm9ikwfOppFmSLpT0NUnLJB3vsask7fI7lxUFuig1vteE/URSzfe6moBs1o6TdKOkVZK+7HefIGmT3/2F"
    "wMBDBjgxoO7A7W+ZoFUTBNjILEqSrpX0J0n3mAmzJW2WVJe0NMyrSapMNeDpdiRV9z9isH8PnL9E0uOSrp6gGiYB+BclrZX0O693"
    "sqTdkl61X0jtA947UdATAVuWdKptLDHoTZL2+j6SrpC030xYOQkVjD7h25I2SPq9zeMav/dHntttZze/aMBJsLHzzVkk3WACVrjf"
    "awmMu100SUeT+YV5kh6W9LKkO3zvMUmjkha6v0DSByT1FC3hRNL7DTi1BF6Q9KZtLJV0XYihvwzET8auMyZdL+kZSa9JWiRpid9/"
    "p8dnSLpY0kkNQmTDlra4s+kBjgcGnSGd55TxV8BOp387gTedJX3Vz2qSqeG4n1/jzKwLWA48BWwGrnE+PgiMmbaWdl6t7of7nPTv"
    "dv8yn/8YmPKsU8SbgP1tbv1k2nYCTxvUx4A5wG+AecBizxsC3gPUmmw/JwX4OOe0A+5/ENgLvOBFPw1sBOb6naUCk/4NzrF7zei/"
    "+t1LQo7e5/HCKh6zzblh76FPM9h+j19ltZpW4A4n23G9FEzpQuA107LI43us3i0BLregWgTJ1S3tucATHk9sy08Dm9wvci+7y6pd"
    "BxZavXdbjbMdVtUmR/AdbVU8ZgEjvq7YiQwHLVnjlhQIVEFlBwIdmWlNC/MqwYYLKfFUw9wD5nZ8tstSrQcuFyVpBTMpuXVbshnD"
    "j2mV2a2GpeHA0UFgn7mdjY+ZqPlW94zItAEhSZP7zdauhrX3AdPtpLaHkDmjVea2CrgfeJc5OQhsAc4wsDrwedv0v90edUknSibN"
    "1auy+wdbu2SAmX1ud2jqAl7xvV7TtadIL73TsW+O++uBE+2t77HTusBqPgO4AvgbcJuJqweVn+OQMieUg5ImjK7b+8+1Gj8ZykHP"
    "+nyK13ijldjfKuBXzemz3F/r8yPAZ73YNnvUHcDrZtJy4C/Ax82cFcA//fx64IaQjeW1QMBXgF8DC6zaPc6yRpx14fA0BLxVRBEv"
    "c/E14LfAi8A3bEObzfkXTahsazVf73f46LXkR03wXhOchZIfAHfYD8RE53bgUzm7H7Sm/cFjs4AHbE7fa1AxnVQcTu20NlhV51ma"
    "9wFft9oNAycBxwZ1lLVii8crBp267bFNXg+cCvzZUjoH+KR9xivATDNqn20V4Oc+X+B4/I8iy7QZ1xZZhe8C7rYNbwwApzf5qjDm"
    "edstVeVstm7NqIaQN+ZWs+2WPbbE9euL/Z57rWVXmiFJETac7Vyet9NYBrzbKd5tBtrTZKFxO5TFVt+tlmy/7X2X1XSbU9UtluIi"
    "4MPA2TafHQ55o8DNBr8UuBR42GBbyt9bLcRnUj7XGdVq4BZL5VFzfCxnIpHbiSW3zgX2cpg74nnv86ZkdoP1B8ywFbbVHjvDsh3i"
    "3pZ3Z5OoRHxf0nCoaCyQ9B9vzEd9Hm/QsuN5ST+TdLvbKkn/CuN1t3GfR3z/fpd1kPRdj12eo63QmlZWb5op6TlJr4da1pkuxWSg"
    "xw7SJOmAqyU7fJ0V77NnD4QmSQ9Jmua1rs3VzEpTWbXMOLnYVcSNljCuIa9V8cdKF/GQ9AkzZZ3LtMlES0iT+ZiWfdy6xHb0EnC1"
    "nVoVuNXVidGD5MxJcIZJLgwqjN9tp4TXeNDx/1InO+8Yd4v6mJap0WUuy/b70whT0GqSvmNpP+Va9ITstl0J5yV9npOQhcAvgB/a"
    "q5ZyO6YYf2OBL21S7BtzSnmn4+9DLg72t/MJtd3vw9nCM4GVwOcca0fCzxvSBpldEnZMMXyNBxUtOXWsAN8Eftrkg/sh/yDeZWmc"
    "6BJPVyCqHohTyImblW+T0GSfsN7xuZCfQhTxo5ZMtc4xmCETl+RUOMlJM23wo5ckl4tn27/TvUlpu4TUroSTAHah894DPld8rvq6"
    "6n53GK/lxnty/Zrz7H5nWfe1q9LlNsFmaneCgQ6ZmFIAFkFk/YrNINss1EOYSoMNV+wP5gNfMmAOl0orp9ZdoXKY+t2ZlGpB2hkD"
    "unw+xuMVj00Lks2YE01Ah9uGR+1Y0lzoSYMtp6Ffykmx3GBuOTi/jM7dRQBOjra/ABT108NkCp9JcvXpIwKwDtEzbR+d30t3AHcA"
    "dwB3AB/Jx9vwOEyKshAiDwAAAABJRU5ErkJggg=="
)
