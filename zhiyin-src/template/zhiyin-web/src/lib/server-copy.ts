import {auth} from './auth'
export function profileLabel(key:string,fallback:string){return auth.state.bootstrap?.copy_bundle?.[`profile.field.${key}`] || fallback}
export function badgeCopy(key:string,part:'label'|'how',fallback:string){return auth.state.bootstrap?.copy_bundle?.[`badge.${key}.${part}`] || fallback}
