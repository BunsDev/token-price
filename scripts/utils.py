import os
from brownie import interface
from brownie.exceptions import ContractNotFound
from datetime import datetime, timedelta
from functools import lru_cache
from typing import List

@lru_cache
def DAI() -> interface.IERC20:
  return interface.IERC20(os.environ.get('DAI_ADDRESS', "0x6b175474e89094c44da98b954eedeac495271d0f"))

@lru_cache
def WETH() -> interface.IERC20:
  return interface.IERC20(os.environ.get('WETH_ADDRESS', "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"))

@lru_cache
def USDT() -> interface.IERC20:
  return interface.IERC20(os.environ.get('USDT_ADDRESS', "0xdac17f958d2ee523a2206206994597c13d831ec7"))

@lru_cache
def USDC() -> interface.IERC20:
  return interface.IERC20(os.environ.get('USDC_ADDRESS', "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"))

@lru_cache
def getFactory(router) -> interface.UniswapFactoryV2:
  return interface.UniswapFactoryV2(router.factory())

@lru_cache
def getToken0(pair) -> interface.IERC20:
  return interface.IERC20(pair.token0())

@lru_cache
def getToken1(pair) -> interface.IERC20:
  return interface.IERC20(pair.token1())

@lru_cache
def getPair(factory, token0, token1) -> interface.UniswapPair:
  return interface.UniswapPair(factory.getPair(token0, token1))

def getReserves(token, otherToken, factory) -> float:
  try:
    pair = getPair(factory, token, otherToken)
  except ContractNotFound:
    return 0

  (token0Reserves, token1Reserves, _) = pair.getReserves()

  if token == getToken0(pair):
    return token0Reserves / 10**(token.decimals())
  else:
    return token1Reserves / 10**(token.decimals())

def getUSDCPath(token: interface.IERC20, router: interface.UniswapRouterV2) -> List[interface.IERC20]:
  factory = getFactory(router)
  if token != WETH():
    reservesInWETH = getReserves(WETH(), token, factory) * priceOf(WETH(), router)
  else:
    reservesInWETH = 0

  reservesInUSDT = getReserves(USDT(), token, factory)
  reservesInUSDC = getReserves(USDC(), token, factory)
  reservesInDAI = getReserves(DAI(), token, factory)

  maxReserves = max(reservesInDAI, reservesInUSDC, reservesInWETH, reservesInUSDT)

  if reservesInDAI == maxReserves:
    return [token, DAI()]
  
  if reservesInWETH == maxReserves:
    return [token, WETH(), USDC()]

  if reservesInUSDT == maxReserves:
    return [token, USDT()]

  return [token, USDC()]

def priceOf(token: interface.IERC20, router_address: str) -> float:
  if token == USDC() or token == USDT():
    return 1.0

  router = interface.UniswapRouterV2(router_address)
  path = getUSDCPath(token, router)
  return router.getAmountsOut(10 ** token.decimals() / 100, path)[-1] / 10 ** path[-1].decimals() * 100

def priceOfUniPair(uni_pair: interface.UniswapPair, router_address: str) -> float:
  (token0Reserves, token1Reserves, _) = uni_pair.getReserves()

  token0 = getToken0(uni_pair)
  token0Price = priceOf(token0, router_address)

  token1 = getToken1(uni_pair)
  token1Price = priceOf(token1, router_address)

  total_pool = token0Reserves * token0Price / 10 ** token0.decimals() + token1Reserves * token1Price / 10 ** token1.decimals()

  return total_pool / uni_pair.totalSupply() * 10 ** uni_pair.decimals()

def priceOf1InchPair(oneinch_pair: interface.IMooniswap, router_address: str) -> float:
  (token0, token1) = oneinch_pair.getTokens()

  if token0 == "0x0000000000000000000000000000000000000000":
    token0 = WETH()
    token0Reserves = oneinch_pair.balance()
  else:
    token0 = interface.IERC20(token0)
    token0Reserves = token0.balanceOf(oneinch_pair)

  if token1 == "0x0000000000000000000000000000000000000000":
    token1 = WETH()
    token1Reserves = oneinch_pair.balance()
  else:
    token1 = interface.IERC20(token1)
    token1Reserves = token1.balanceOf(oneinch_pair)


  token0Price = priceOf(token0, router_address)
  token1Price = priceOf(token1, router_address)

  total_pool = token0Reserves * token0Price / 10 ** token0.decimals() + token1Reserves * token1Price / 10 ** token1.decimals()

  return total_pool / oneinch_pair.totalSupply() * 10 ** oneinch_pair.decimals()

def priceOfCurveLPToken(lp_token: interface.CurveLPToken, router_address: str) -> float:
  minter = interface.CurveLPMinter(lp_token.minter())

  total_supply = lp_token.totalSupply() / 10 ** 18

  total_dollars_locked = 0
  for i in range(5):
    try:
      coin = interface.ERC20(minter.coins(i))
      total_dollars_locked += priceOf(coin, router_address) * minter.balances(i) / 10 ** coin.decimals()
    except ValueError:
      break

  return total_dollars_locked / total_supply

def priceOfCurvePool(lp_token: interface.CurvePool, router_address: str) -> float:
  total_supply = lp_token.totalSupply() / 10 ** 18

  total_dollars_locked = 0
  for i in range(5):
    try:
      coin = interface.ERC20(lp_token.coins(i))
      total_dollars_locked += priceOf(coin, router_address) * lp_token.balances(i) / 10 ** coin.decimals()
    except ValueError:
      break

  return total_dollars_locked / total_supply

def homoraV2PositionSize(pos_id: int, bank_address: str, router_address: str) -> float:
  bank = interface.HomoraBank(bank_address)

  (_owner, coll_token, coll_id, coll_size) = bank.getPositionInfo(pos_id)
  coll = interface.WMasterChef(coll_token)

  underlying_lp_token = interface.UniswapPair(coll.getUnderlyingToken(coll_id))
  position_size = priceOfUniPair(underlying_lp_token, router_address) * coll_size / 10 ** underlying_lp_token.decimals()

  debts = bank.getPositionDebts(pos_id)
  total_debt = 0

  for (debt_token, debt_size) in zip(*debts):
    debt_token = interface.ERC20(debt_token)
    total_debt += priceOf(debt_token, router_address) * debt_size / 10 ** debt_token.decimals()

  return position_size - total_debt
